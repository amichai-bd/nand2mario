"""One outstanding request, strict replies, and no automatic replay."""
import hashlib
import time
import zlib

from .. import generated_interfaces as abi
from ..interface_codec import (SDRAM_LINE, checked_range, decode_packet, encode_packet, pack_record, peek_store,
                               sdram_line_address, sdram_read, sdram_write, unpack_record, uint)


class UncertainCompletion(RuntimeError):
    """The endpoint may have acted; this session cannot issue another request."""


class RejectedCommand(RuntimeError):
    def __init__(self, command, status):
        self.command, self.status = command, status
        super().__init__(f'{command} rejected with status {status}')


# The frozen DMG I/O view; the host SPEC owns its read semantics and evidence.
IO_REGISTERS = ('LCDC', 'STAT', 'SCY', 'SCX', 'LY', 'LYC', 'BGP', 'OBP0', 'OBP1',
                'WY', 'WX', 'DIV', 'TIMA', 'TMA', 'TAC', 'IF', 'IE')


def summary(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


class Client:
    def __init__(self, transport, *, sequence=0, record=None, persist=None, clock=time.monotonic):
        self.transport = transport
        self.sequence = uint(sequence, next(f['bits'] for f in abi.RECORDS['packet_header'] if f['name'] == 'seq'))
        self.sequence_mask = (1 << next(f['bits'] for f in abi.RECORDS['packet_header'] if f['name'] == 'seq')) - 1
        self.record = record or (lambda entry: None)
        self.persist = persist or (lambda sequence, pending: None)
        self.clock = clock
        self.uncertain = False

    def request(self, name, payload=b'', *, count=None):
        if self.uncertain:
            raise UncertainCompletion('session stopped after uncertain completion; no request sent')
        definition = next(item for item in abi.COMMANDS if item['name'] == name)
        command = getattr(abi, 'COMMAND_' + name)
        packet = encode_packet(self.sequence, command, payload)
        sequence = self.sequence
        self.sequence = (sequence + 1) & self.sequence_mask
        # Reserve durably before any write. A crash cannot silently replay a token.
        self.persist(self.sequence, True)
        self.uncertain = True
        self.record({'event': 'request', 'command': name, 'sequence': sequence, 'payload': summary(payload)})
        try:
            deadline = self.clock() + abi.WIRE_RESPONSE_TIMEOUT_MS / 1000
            if self.transport.write(packet) != len(packet):
                raise OSError('short request write')
            raw_max = abi.PACKET_HEADER_BYTES + abi.WIRE_MAX_PAYLOAD + 2
            maximum = raw_max + raw_max // 254 + 2
            frame = bytearray()
            while True:
                remaining = deadline - self.clock()
                if remaining <= 0:
                    raise TimeoutError('response timeout')
                self.transport.timeout = remaining
                byte = self.transport.read(1)
                if not byte:
                    raise TimeoutError('response timeout')
                if len(byte) != 1:
                    raise ValueError('transport violated bounded read')
                if byte == b'\0' and not frame:
                    continue
                frame.extend(byte)
                if len(frame) > maximum:
                    raise ValueError('oversized response')
                if byte == b'\0':
                    break
            header, response = decode_packet(bytes(frame))
            if header['kind'] != abi.WIRE_RESPONSE or header['seq'] != sequence or header['command'] != command:
                raise ValueError('response does not match outstanding request')
            known_statuses = {getattr(abi, key) for key in vars(abi) if key.startswith('STATUS_')}
            if header['status'] not in known_statuses:
                raise ValueError('unknown response status')
            if header['status'] != abi.STATUS_OK:
                if response:
                    raise ValueError('error response contains payload')
                result = None
            elif definition['response'] == 'empty':
                if response:
                    raise ValueError('unexpected response payload')
                result = None
            elif definition['response'] == 'bytes':
                if len(response) != count:
                    raise ValueError('read response length mismatch')
                result = response
            else:
                result = unpack_record(definition['response'], response)
            if name == 'RUN_DOTS' and header['status'] == abi.STATUS_OK:
                requested = unpack_record('word', payload)['value']
                complete = result['reason'] == abi.WIRE_RUN_DOTS_COUNT and result['executed'] == requested
                stopped = result['reason'] == abi.WIRE_RUN_DOTS_STOPPED and result['executed'] < requested
                if not (complete or stopped):
                    raise ValueError('invalid RUN_DOTS completion')
            self.record({'event': 'response', 'command': name, 'sequence': sequence,
                         'status': header['status'], 'payload': summary(response),
                         'fields': result if isinstance(result, dict) else None})
            self.persist(self.sequence, False)
            self.uncertain = False
        except Exception as error:
            self.record({'event': 'uncertain', 'command': name, 'sequence': sequence, 'reason': str(error)})
            raise UncertainCompletion(f'{name}: uncertain completion ({error}); no automatic replay') from error
        if header['status'] != abi.STATUS_OK:
            raise RejectedCommand(name, header['status'])
        return result

    def read_host(self, address):
        from ..interface_codec import host_address
        return self.request('READ_HOST', pack_record('read_host', {'address': host_address(address)}))['value']

    def read_io_registers(self):
        """One live read per exposed DMG register; no pause and no state change."""
        return {name: self.read_host(getattr(abi, 'HOST_REG_IO_' + name)) for name in IO_REGISTERS}

    def read_lcd_status(self):
        """LCDC, STAT and LY sampled on one endpoint edge, so the triple is coherent."""
        word = self.read_host(abi.HOST_REG_IO_LCD_STATUS)
        return {'ly': word & 0xFF, 'stat': (word >> 8) & 0xFF,
                'lcdc': (word >> 16) & 0xFF, 'mode': (word >> 8) & 0x3}

    def sample_io(self, samples):
        """Repeated live LCD samples with the dot each was taken at."""
        if type(samples) is not int or not 1 <= samples <= 5000:
            raise ValueError('sample count outside 1..5000')
        rows = []
        for _ in range(samples):
            row = self.read_lcd_status()
            row['dot_lo'] = self.read_host(abi.HOST_REG_DOT_LO)
            rows.append(row)
        return {'samples': rows, 'registers': self.read_io_registers()}

    def write_host(self, address, value):
        from ..interface_codec import host_write
        return self.request('WRITE_HOST', host_write(address, value))

    def select_input_source(self, source):
        return self.write_host(abi.HOST_REG_INPUT_SOURCE, source)

    def identify(self):
        ping = self.request('PING')['value']
        version = self.read_host(abi.HOST_REG_ABI)
        if ping != abi.WIRE_ABI or version != abi.WIRE_ABI:
            raise ValueError('endpoint ABI mismatch')
        words = [self.read_host(getattr(abi, f'HOST_REG_BUILD_ID_{i}')) for i in range(4)]
        if not any(words):
            raise ValueError('endpoint build identity is zero; physical host commands require an identified build')
        return {'abi': version, 'build_id': b''.join(word.to_bytes(4, 'little') for word in words).hex()}

    def load(self, image, *, progress=None):
        """Load and verify one image, optionally reporting completed bytes.

        The callback receives dictionaries with ``stage``, ``completed`` and
        ``total``.  Upload bytes count only after LOAD_WRITE is acknowledged;
        readback bytes count only after READ_ROM returns them.  Omitting the
        callback preserves the original request sequence and result.
        """
        image = bytes(image)
        if len(image) != abi.PROFILE_ROM_BYTES:
            raise ValueError('wrong direct-profile image size')
        notify = progress or (lambda _event: None)
        self.request('LOAD_BEGIN', pack_record('load_begin', {
            'profile': abi.PROFILE_DIRECT_ID, 'size': len(image), 'crc32': zlib.crc32(image)}))
        chunk = abi.WIRE_MAX_PAYLOAD - abi.OFFSET_BYTES
        notify({'stage': 'upload', 'completed': 0, 'total': len(image)})
        for offset in range(0, len(image), chunk):
            data = image[offset:offset + chunk]
            self.request('LOAD_WRITE', pack_record('offset', {'offset': offset}) + data)
            notify({'stage': 'upload', 'completed': offset + len(data), 'total': len(image)})
        self.request('LOAD_END')
        readback = self.read_storage('READ_ROM', len(image), progress=notify, stage='readback')
        if readback != image:
            # Never include private byte values in a failure record.
            mismatch = next(i for i, (actual, expected) in enumerate(zip(readback, image)) if actual != expected)
            raise ValueError(f'full ROM readback mismatch at offset {mismatch}')
        if self.read_host(abi.HOST_REG_PROFILE) != abi.PROFILE_DIRECT_ID:
            raise ValueError('loaded endpoint profile mismatch')
        if self.read_host(abi.HOST_REG_IMAGE_VALID) != 1 or self.read_host(abi.HOST_REG_STATE) != abi.STATE_PAUSED:
            raise ValueError('verified load did not leave a valid paused image')
        return {'verified_bytes': len(image), 'image': summary(image)}

    def read_storage(self, command, size, *, progress=None, stage=None):
        """Read a whole store, optionally reporting bytes returned by the wire."""
        if (progress is None) != (stage is None):
            raise ValueError('read progress requires both callback and stage')
        notify = progress or (lambda _event: None)
        result = bytearray()
        if progress is not None:
            notify({'stage': stage, 'completed': 0, 'total': size})
        for offset in range(0, size, abi.WIRE_MAX_PAYLOAD):
            count = min(abi.WIRE_MAX_PAYLOAD, size - offset)
            checked_range(offset, count, size)
            result.extend(self.request(command, pack_record('read_range', {'offset': offset, 'count': count}), count=count))
            if progress is not None:
                notify({'stage': stage, 'completed': len(result), 'total': size})
        return bytes(result)

    def peek_range(self, store, offset, count):
        """Read one bounded range of a non-ROM store from a paused core.

        Read-only by construction: the endpoint serves peek from port B, which
        has no write. A held snapshot is neither consumed nor disturbed. One
        request covers at most WIRE_MAX_PAYLOAD bytes; the range is checked
        against the store before anything is sent.
        """
        selector, size = peek_store(store)
        checked_range(offset, count, size)
        return self.request('PEEK', pack_record(
            'peek_range', {'store': selector, 'offset': offset, 'count': count}), count=count)

    def peek(self, store):
        """Read one whole non-ROM store from a paused core, in wire chunks."""
        _selector, size = peek_store(store)
        result = bytearray()
        for offset in range(0, size, abi.WIRE_MAX_PAYLOAD):
            count = min(abi.WIRE_MAX_PAYLOAD, size - offset)
            result.extend(self.peek_range(store, offset, count))
        return {'store': store, 'bytes': size}, bytes(result)

    def control(self, action, value=None):
        if action in ('STEP', 'RUN_DOTS'):
            maximum = abi.WIRE_STEP_MAX_DOTS if action == 'STEP' else abi.WIRE_RUN_DOTS_MAX
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError('dot budget outside generated bounds')
            payload = pack_record('word', {'value': value})
        elif action == 'INPUT':
            payload = pack_record('input', {'buttons': value})
        elif action in ('RESET', 'RUN', 'HALT'):
            payload = b''
        else:
            raise ValueError('unknown host control')
        return self.request(action, payload)

    def run_dots(self, count):
        return self.control('RUN_DOTS', count)

    def snapshot(self):
        metadata = self.request('SNAPSHOT')
        if metadata['size'] != abi.FRAME_BYTES:
            raise ValueError('snapshot size differs from generated frame ABI')
        pixels = self.read_storage('READ_FRAME', metadata['size'])
        # The dedicated snapshot survives core reset and new source frames. No
        # second SNAPSHOT is sent while chunks are being retrieved.
        return metadata, pixels

    def sdram_write(self, address, line):
        """Write one 16-byte line at a line-aligned device address."""
        return self.request('SDRAM_WRITE', sdram_write(address, line))

    def sdram_read(self, address, lines=1):
        """Read 1..15 consecutive lines; returns exactly lines*16 bytes."""
        return self.request('SDRAM_READ', sdram_read(address, lines), count=lines * SDRAM_LINE)

    def sdram_test(self, start, length, *, seed=1, progress=None, mismatch_limit=64):
        """Write a seeded pattern over a line range, read it back and compare.

        Writes go one line per SDRAM_WRITE and reads fifteen lines per
        SDRAM_READ. The pattern is derived from the seed and the line address
        so a stale or aliased line never matches by accident. Every mismatch is
        reported by device address with expected and actual bytes, up to
        ``mismatch_limit`` detailed entries; the count is always complete.
        """
        if type(start) is not int or type(length) is not int or length <= 0 or start % SDRAM_LINE or length % SDRAM_LINE:
            raise ValueError('SDRAM test range must be line aligned and nonempty')
        sdram_line_address(start)
        if start + length > abi.SDRAM_BYTES:
            raise ValueError('SDRAM test range exceeds the device')
        notify = progress or (lambda _event: None)
        lines = length // SDRAM_LINE
        notify({'stage': 'write', 'completed': 0, 'total': lines})
        for index in range(lines):
            address = start + index * SDRAM_LINE
            self.sdram_write(address, sdram_pattern(address, seed))
            if index % 256 == 255 or index == lines - 1:
                notify({'stage': 'write', 'completed': index + 1, 'total': lines})
        mismatches = []
        mismatch_count = 0
        compared = 0
        notify({'stage': 'read', 'completed': 0, 'total': lines})
        for index in range(0, lines, abi.SDRAM_READ_MAX_LINES):
            count = min(abi.SDRAM_READ_MAX_LINES, lines - index)
            address = start + index * SDRAM_LINE
            actual = self.sdram_read(address, count)
            expected = b''.join(sdram_pattern(address + i * SDRAM_LINE, seed) for i in range(count))
            if actual != expected:
                for i in range(count):
                    got, want = actual[i * SDRAM_LINE:(i + 1) * SDRAM_LINE], expected[i * SDRAM_LINE:(i + 1) * SDRAM_LINE]
                    if got != want:
                        mismatch_count += 1
                        if len(mismatches) < mismatch_limit:
                            mismatches.append({'address': address + i * SDRAM_LINE, 'expected': want.hex(), 'actual': got.hex()})
            compared += count
            if compared % (abi.SDRAM_READ_MAX_LINES * 64) < abi.SDRAM_READ_MAX_LINES or compared == lines:
                notify({'stage': 'read', 'completed': compared, 'total': lines})
        return {'start': start, 'length': length, 'lines': lines, 'seed': seed,
                'mismatch_count': mismatch_count, 'mismatches': mismatches,
                'status': 'PASS' if mismatch_count == 0 else 'FAIL'}


# The storage contract's boundary set (wiki/src/rtl/storage/MAS_sdram.md#verification):
# first and last line of slots 0, 15 and 16, first and last catalogue line,
# first and last line of a row, one line in each bank including the device end.
SDRAM_BOUNDARY_LINES = (
    ('slot 0 first', 0x0000000), ('slot 0 last', 0x0007FF0),
    ('slot 15 first', 0x0078000), ('slot 15 last', 0x007FFF0),
    ('slot 16 first', 0x0080000), ('slot 16 last', 0x0087FF0),
    ('catalogue first', 0x0088000), ('catalogue last', 0x00883F0),
    ('row first', 0x1002800), ('row last', 0x1002FF0),
    ('bank 0', 0x0000010), ('bank 1', 0x1ABC800), ('bank 2', 0x2000FF0), ('bank 3 device end', 0x3FFFFF0),
)


def sdram_boundary_test(client, *, seed=1):
    """Write every boundary line, then read each back and compare by address."""
    for _name, address in SDRAM_BOUNDARY_LINES:
        client.sdram_write(address, sdram_pattern(address, seed))
    mismatches = []
    for name, address in SDRAM_BOUNDARY_LINES:
        actual = client.sdram_read(address, 1)
        expected = sdram_pattern(address, seed)
        if actual != expected:
            mismatches.append({'name': name, 'address': address, 'expected': expected.hex(), 'actual': actual.hex()})
    return {'mode': 'boundary', 'lines': len(SDRAM_BOUNDARY_LINES), 'seed': seed,
            'addresses': {name: address for name, address in SDRAM_BOUNDARY_LINES},
            'mismatch_count': len(mismatches), 'mismatches': mismatches,
            'status': 'PASS' if not mismatches else 'FAIL'}


def sdram_pattern(address, seed):
    """The 16-byte test line for one device address: address- and seed-dependent, no two lines alike."""
    line = bytearray()
    state = (address // SDRAM_LINE) * 2654435761 + seed * 40503 + 0x9e3779b9
    for index in range(SDRAM_LINE):
        state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        line.append(((state >> 33) ^ (address >> 4) ^ index) & 0xFF)
    return bytes(line)
