"""One outstanding request, strict replies, and no automatic replay."""
import hashlib
import time
import zlib

from .. import generated_interfaces as abi
from ..interface_codec import checked_range, decode_packet, encode_packet, pack_record, unpack_record, uint


class UncertainCompletion(RuntimeError):
    """The endpoint may have acted; this session cannot issue another request."""


class RejectedCommand(RuntimeError):
    def __init__(self, command, status):
        self.command, self.status = command, status
        super().__init__(f'{command} rejected with status {status}')


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

    def load(self, image):
        image = bytes(image)
        if len(image) != abi.PROFILE_ROM_BYTES:
            raise ValueError('wrong direct-profile image size')
        self.request('LOAD_BEGIN', pack_record('load_begin', {
            'profile': abi.PROFILE_DIRECT_ID, 'size': len(image), 'crc32': zlib.crc32(image)}))
        chunk = abi.WIRE_MAX_PAYLOAD - abi.OFFSET_BYTES
        for offset in range(0, len(image), chunk):
            self.request('LOAD_WRITE', pack_record('offset', {'offset': offset}) + image[offset:offset + chunk])
        self.request('LOAD_END')
        readback = self.read_storage('READ_ROM', len(image))
        if readback != image:
            # Never include private byte values in a failure record.
            mismatch = next(i for i, (actual, expected) in enumerate(zip(readback, image)) if actual != expected)
            raise ValueError(f'full ROM readback mismatch at offset {mismatch}')
        if self.read_host(abi.HOST_REG_PROFILE) != abi.PROFILE_DIRECT_ID:
            raise ValueError('loaded endpoint profile mismatch')
        if self.read_host(abi.HOST_REG_IMAGE_VALID) != 1 or self.read_host(abi.HOST_REG_STATE) != abi.STATE_PAUSED:
            raise ValueError('verified load did not leave a valid paused image')
        return {'verified_bytes': len(image), 'image': summary(image)}

    def read_storage(self, command, size):
        result = bytearray()
        for offset in range(0, size, abi.WIRE_MAX_PAYLOAD):
            count = min(abi.WIRE_MAX_PAYLOAD, size - offset)
            checked_range(offset, count, size)
            result.extend(self.request(command, pack_record('read_range', {'offset': offset, 'count': count}), count=count))
        return bytes(result)

    def control(self, action, value=None):
        if action == 'STEP':
            if type(value) is not int or not 1 <= value <= abi.WIRE_STEP_MAX_DOTS:
                raise ValueError('step budget outside generated bounds')
            payload = pack_record('word', {'value': value})
        elif action == 'INPUT':
            payload = pack_record('input', {'buttons': value})
        elif action in ('RESET', 'RUN', 'HALT'):
            payload = b''
        else:
            raise ValueError('unknown host control')
        return self.request(action, payload)

    def snapshot(self):
        metadata = self.request('SNAPSHOT')
        if metadata['size'] != abi.FRAME_BYTES:
            raise ValueError('snapshot size differs from generated frame ABI')
        pixels = self.read_storage('READ_FRAME', metadata['size'])
        # The dedicated snapshot survives core reset and new source frames. No
        # second SNAPSHOT is sent while chunks are being retrieved.
        return metadata, pixels
