"""Byte-level fake endpoint checks. No serial port or licensed tool is opened."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import generated_interfaces as abi
from n2m.cli import main
from n2m.doctor import select_uart
from n2m.host.client import IO_REGISTERS, Client, RejectedCommand, UncertainCompletion
from n2m.host.package import read_package
from n2m.host.transport import SerialTransport, open_serial, session
from n2m import interface_codec
from n2m.interface_codec import decode_packet, encode_packet, pack_record, unpack_record
from n2m.records import atomic_json, file_hash
from sw.package import package
from sw.rom_build import build_target

ROOT = Path(__file__).resolve().parents[3]
DEVICE = {'DeviceID': 'COM92', 'PNPDeviceID': 'USB\\VID_1234&PID_5678\\ORIGINAL_FAKE',
          'Status': 'OK', 'ConfigManagerErrorCode': 0}


class Endpoint:
    """Independent command-state fake. Shared codecs only serialize the wire."""
    def __init__(self, defect=None):
        self.defect = defect
        self.requests = []
        self.pending = bytearray()
        self.rom = bytearray(abi.PROFILE_ROM_BYTES)
        self.present = set()
        self.state = abi.STATE_PAUSED
        self.valid = 0
        self.profile = 0
        self.buttons = 0
        self.dot = 0
        self.line = 0
        self.expected_crc = None
        self.frame = bytes((index * 37 + 11) % 256 for index in range(abi.FRAME_BYTES))
        self.stores = {selector: bytes((index * 13 + selector * 7) % 256 for index in range(size))
                       for selector, size in interface_codec.PEEK_STORES.values()}
        self.snapshot_calls = 0
        self.closed = False
        self.timeout = 2

    def write(self, packet):
        header, payload = decode_packet(packet)
        name = next(item['name'] for item in abi.COMMANDS if getattr(abi, 'COMMAND_' + item['name']) == header['command'])
        self.requests.append((name, payload, header['seq']))
        status, response = abi.STATUS_OK, b''
        if name == 'PING':
            response = pack_record('word', {'value': abi.WIRE_ABI})
        elif name == 'READ_HOST':
            address = unpack_record('read_host', payload)['address']
            values = {abi.HOST_REG_ABI: abi.WIRE_ABI, abi.HOST_REG_STATE: self.state,
                      abi.HOST_REG_IMAGE_VALID: self.valid, abi.HOST_REG_PROFILE: self.profile,
                      abi.HOST_REG_INPUT: self.buttons}
            values.update({getattr(abi, f'HOST_REG_BUILD_ID_{i}'): 0x12340000 + i for i in range(4)})
            # A live DMG view: each read advances the fake's own scanline model,
            # which the endpoint's real registers do on their own.
            from n2m.host.client import IO_REGISTERS
            values.update({getattr(abi, 'HOST_REG_IO_' + name): index for index, name in enumerate(IO_REGISTERS)})
            values[abi.HOST_REG_IO_LY] = self.line
            values[abi.HOST_REG_IO_STAT] = 0x40 | (1 if self.line >= 144 else 3)
            values[abi.HOST_REG_IO_LCDC] = 0x91
            values[abi.HOST_REG_IO_LCD_STATUS] = (0x91 << 16) | (values[abi.HOST_REG_IO_STAT] << 8) | self.line
            values[abi.HOST_REG_DOT_LO] = self.dot
            if address in (abi.HOST_REG_IO_LCD_STATUS, abi.HOST_REG_IO_LY):
                self.line = (self.line + 7) % 154
                self.dot += 456
            if self.defect == 'zero-build':
                values.update({getattr(abi, f'HOST_REG_BUILD_ID_{i}'): 0 for i in range(4)})
            response = pack_record('word', {'value': values[address]})
        elif name == 'LOAD_BEGIN':
            request = unpack_record('load_begin', payload)
            if request['profile'] != abi.PROFILE_DIRECT_ID or request['size'] != len(self.rom):
                status = abi.STATUS_BAD_VALUE
            else:
                self.profile = request['profile']
                self.expected_crc = request['crc32']
                self.state = abi.STATE_LOADING
                self.valid = 0
                self.present.clear()
        elif name == 'LOAD_WRITE':
            if self.state != abi.STATE_LOADING:
                status = abi.STATUS_BAD_STATE
            else:
                offset = int.from_bytes(payload[:4], 'little')
                data = payload[4:]
                assert data and offset + len(data) <= len(self.rom)
                self.rom[offset:offset + len(data)] = data
                self.present.update(range(offset, offset + len(data)))
        elif name == 'LOAD_END':
            if len(self.present) != len(self.rom) or zlib.crc32(self.rom) != self.expected_crc:
                status = abi.STATUS_BAD_IMAGE
            else:
                self.valid, self.state = 1, abi.STATE_PAUSED
        elif name in ('READ_ROM', 'READ_FRAME'):
            request = unpack_record('read_range', payload)
            offset, count = request['offset'], request['count']
            storage = self.rom if name == 'READ_ROM' else self.frame
            response = bytes(storage[offset:offset + count])
            if self.defect == 'mismatch' and name == 'READ_ROM' and offset == 32512:
                response = response[:-1] + bytes([response[-1] ^ 1])
        elif name == 'RUN':
            self.state = abi.STATE_RUNNING
        elif name == 'HALT':
            self.state = abi.STATE_PAUSED
            response = pack_record('dot', {'dot': self.dot})
        elif name == 'RESET':
            self.state, self.dot, self.buttons = abi.STATE_PAUSED, 0, 0
        elif name == 'STEP':
            budget = unpack_record('word', payload)['value']
            self.dot += min(4, budget)
            self.state = abi.STATE_PAUSED
            if budget < 4:
                status = abi.STATUS_STEP_LIMIT
            else:
                response = pack_record('dot', {'dot': self.dot})
        elif name == 'INPUT':
            self.buttons = unpack_record('input', payload)['buttons']
            response = pack_record('dot', {'dot': self.dot})
        elif name == 'PEEK':
            request = unpack_record('peek_range', payload)
            selector, offset, count = request['store'], request['offset'], request['count']
            if self.state != abi.STATE_PAUSED:
                status = abi.STATUS_BAD_STATE
            elif selector not in self.stores or offset + count > len(self.stores[selector]):
                status = abi.STATUS_BAD_VALUE
            else:
                response = bytes(self.stores[selector][offset:offset + count])
        elif name == 'SNAPSHOT':
            self.snapshot_calls += 1
            response = pack_record('snapshot', {'epoch': 3, 'seq': 0x100000002, 'dot': 0x100000003,
                                                 'size': len(self.frame)})
        if self.defect == 'timeout' or self.defect == 'short-write':
            return len(packet) if self.defect == 'timeout' else len(packet) - 1
        if self.defect == 'sequence':
            header['seq'] += 1
        if self.defect == 'length':
            response += b'\1'
        frame = encode_packet(header['seq'], header['command'], response, kind=abi.WIRE_RESPONSE, status=status)
        if self.defect == 'crc':
            frame = frame[:-3] + bytes([frame[-3] ^ 1]) + frame[-2:]
        self.pending.extend(frame)
        return len(packet)

    def read(self, count):
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result

    def close(self):
        self.closed = True


class HostTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'workdir/builds/host-unit'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='path with spaces ', dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.args = SimpleNamespace(uart_port='COM92', uart_vid=None, uart_pid=None, uart_identity=None,
                                    endpoint_restarted=False)

    def image(self):
        image = bytearray((index * 13 + index // 256) % 256 for index in range(32768))
        image[256:336] = bytes([255]) * 80
        return package({'image': image, 'entry': 512}, 'HOST FIXTURE', 1)

    def manifest(self):
        folder = self.folder / 'sw/build/original/runs/123456789abc'
        folder.mkdir(parents=True)
        rom = folder / 'image.gb'
        rom.write_bytes(self.image())
        name = rom.relative_to(ROOT).as_posix()
        record = {'status': 'PASS', 'attempt': folder.name, 'profile': abi.PROFILE_NAME,
                  'entry': 512, 'rom': name, 'artifacts': {name: file_hash(rom)},
                  'inputs': {name: file_hash(ROOT / name) for name in
                             ('cfg/interfaces.json', 'tools/n2m/generated_interfaces.py')}}
        path = folder / 'result.json'
        atomic_json(path, record)
        return path, record

    def test_host_write_validates_before_transport(self):
        endpoint = Endpoint()
        client = Client(endpoint)
        for address, value in ((0x10000, 0), (0x10048, 1), (0x1004c, 0),
                               (0x10020, 256), (0x10044, 2), (0xff00, 1)):
            with self.assertRaises(ValueError):
                client.write_host(address, value)
        self.assertEqual(endpoint.requests, [])
        self.assertEqual(client.sequence, 0)
        self.assertFalse(client.uncertain)
        with patch.object(client, 'request', return_value={'dot': 17}) as request:
            self.assertEqual(client.write_host(0x10020, 0xa5), {'dot': 17})
            request.assert_called_once_with('WRITE_HOST', bytes.fromhex('20 00 01 00 a5 00 00 00'))
        with patch.object(client, 'request', return_value={'dot': 18}) as request:
            self.assertEqual(client.select_input_source(1), {'dot': 18})
            request.assert_called_once_with('WRITE_HOST', bytes.fromhex('44 00 01 00 01 00 00 00'))

    def test_live_io_registers_read_without_pausing(self):
        endpoint = Endpoint()
        endpoint.state = abi.STATE_RUNNING
        client = Client(endpoint)
        result = client.sample_io(30)
        self.assertEqual(len(result['samples']), 30)
        # Reads are ordinary READ_HOST commands; nothing pauses or steps.
        self.assertEqual({name for name, _, _ in endpoint.requests}, {'READ_HOST'})
        self.assertEqual(endpoint.state, abi.STATE_RUNNING)
        for row in result['samples']:
            self.assertEqual(row['lcdc'], 0x91)
            self.assertLess(row['stat'], 0x80)
            self.assertLessEqual(row['ly'], 153)
            self.assertEqual(row['ly'] >= 144, row['mode'] == 1)
        dots = [row['dot_lo'] for row in result['samples']]
        self.assertEqual(dots, sorted(dots))
        self.assertGreaterEqual(len({row['ly'] for row in result['samples']}), 20)
        self.assertEqual(sorted(result['registers']), sorted(IO_REGISTERS))
        for count in (0, 5001, 'many'):
            with self.assertRaises(ValueError):
                client.sample_io(count)

    def test_complete_load_readback_and_controls(self):
        endpoint = Endpoint()
        records = []
        client = Client(endpoint, record=records.append)
        self.assertEqual(client.identify()['build_id'], '00003412010034120200341203003412')
        image = self.image()
        result = client.load(image)
        self.assertEqual(result['verified_bytes'], 32768)
        self.assertEqual(endpoint.rom, image)
        reads = [unpack_record('read_range', payload) for name, payload, seq in endpoint.requests if name == 'READ_ROM']
        self.assertEqual(reads, [{'offset': offset, 'count': 256} for offset in range(0, 32768, 256)])
        writes = [payload for name, payload, seq in endpoint.requests if name == 'LOAD_WRITE']
        self.assertEqual(b''.join(payload[4:] for payload in writes), image)
        self.assertEqual(len(writes[-1]), 12)
        client.control('RUN')
        self.assertEqual(endpoint.state, abi.STATE_RUNNING)
        client.control('HALT')
        self.assertEqual(client.control('STEP', 4), {'dot': 4})
        client.control('RESET')
        self.assertEqual((endpoint.dot, endpoint.state), (0, abi.STATE_PAUSED))
        self.assertNotIn(image[:20].hex(), json.dumps(records))

    def test_peek_reads_every_store_in_chunks_and_leaves_a_snapshot_held(self):
        endpoint = Endpoint()
        client = Client(endpoint)
        for store, (selector, size) in sorted(interface_codec.PEEK_STORES.items()):
            metadata, contents = client.peek(store)
            self.assertEqual(metadata, {'store': store, 'bytes': size})
            self.assertEqual(contents, endpoint.stores[selector])
            requests = [unpack_record('peek_range', payload)
                        for name, payload, seq in endpoint.requests if name == 'PEEK']
            chunks = [r for r in requests if r['store'] == selector]
            # Exactly the chunked shape LOAD_READ and READ_FRAME already use.
            self.assertEqual(sum(r['count'] for r in chunks), size)
            self.assertEqual([r['offset'] for r in chunks],
                             list(range(0, size, abi.WIRE_MAX_PAYLOAD)))
            self.assertTrue(all(1 <= r['count'] <= abi.WIRE_MAX_PAYLOAD for r in chunks))
        # Peek and snapshot readback are independent: a peek between the
        # capture and its chunks neither consumes nor disturbs the snapshot.
        metadata, pixels = client.snapshot()
        self.assertEqual(pixels, endpoint.frame)
        client.peek('wram')
        again, pixels_again = client.snapshot()
        self.assertEqual((again, pixels_again), (metadata, pixels))

    def test_peek_rejects_unknown_stores_and_an_unpaused_core(self):
        endpoint = Endpoint()
        client = Client(endpoint)
        # An unknown store never reaches the wire at all.
        for name in ('rom', 'io', '', 'WRAM'):
            with self.assertRaises(ValueError):
                client.peek(name)
        self.assertEqual([r for r in endpoint.requests if r[0] == 'PEEK'], [])
        client.control('RUN')
        with self.assertRaises(RejectedCommand) as rejected:
            client.peek('wram')
        self.assertEqual(rejected.exception.status, abi.STATUS_BAD_STATE)
        client.control('HALT')
        self.assertEqual(client.peek('hram')[1], endpoint.stores[abi.PEEK_HRAM])

    def test_all_input_masks_and_immutable_frame(self):
        endpoint = Endpoint()
        client = Client(endpoint)
        for mask in range(256):
            self.assertEqual(client.control('INPUT', mask), {'dot': 0})
            self.assertEqual(endpoint.buttons, mask)
            self.assertEqual(client.read_host(abi.HOST_REG_INPUT), mask)
        metadata, pixels = client.snapshot()
        self.assertEqual(metadata, {'epoch': 3, 'seq': 4294967298, 'dot': 4294967299, 'size': 5760})
        self.assertEqual(pixels, endpoint.frame)
        self.assertEqual(endpoint.snapshot_calls, 1)
        frame_reads = [unpack_record('read_range', payload) for name, payload, seq in endpoint.requests if name == 'READ_FRAME']
        self.assertEqual(frame_reads[-1], {'offset': 5632, 'count': 128})

    def test_mismatch_last_byte_stops_without_run(self):
        endpoint = Endpoint('mismatch')
        with self.assertRaisesRegex(ValueError, 'offset 32767'):
            Client(endpoint).load(self.image())
        self.assertNotIn('RUN', [name for name, _, _ in endpoint.requests])

    def test_uncertain_failures_never_replay_or_continue(self):
        for defect in ('timeout', 'short-write', 'sequence', 'crc', 'length'):
            with self.subTest(defect=defect):
                endpoint = Endpoint(defect)
                persisted = []
                client = Client(endpoint, persist=lambda *args: persisted.append(args))
                with self.assertRaises(UncertainCompletion):
                    client.request('PING')
                with self.assertRaises(UncertainCompletion):
                    client.request('PING')
                self.assertEqual(len(endpoint.requests), 1)
                self.assertEqual(persisted, [(1, True)])

    def test_known_step_limit_and_bounds(self):
        endpoint = Endpoint()
        client = Client(endpoint)
        for action, value in [('STEP', 0), ('STEP', 70225), ('INPUT', 256), ('INPUT', -1)]:
            with self.assertRaises(ValueError):
                client.control(action, value)
        with self.assertRaises(ValueError):
            client.load(b'wrong size')
        self.assertEqual(endpoint.requests, [])
        with self.assertRaises(RejectedCommand) as raised:
            client.control('STEP', 1)
        self.assertEqual(raised.exception.status, abi.STATUS_STEP_LIMIT)
        self.assertFalse(client.uncertain)
        self.assertEqual(endpoint.dot, 1)

    def test_immutable_package_and_rejections_before_open(self):
        path, record = self.manifest()
        self.assertEqual(read_package(ROOT, path)[0], self.image())
        mutations = [('profile', 'wrong'), ('status', 'FAIL'), ('attempt', 'aaaaaaaaaaaa')]
        for key, value in mutations:
            bad = {**record, key: value}
            atomic_json(path, bad)
            with self.assertRaises(ValueError):
                read_package(ROOT, path)
        atomic_json(path, record)
        rom = ROOT / record['rom']
        rom.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            read_package(ROOT, path)
        record['artifacts'][record['rom']] = file_hash(rom)
        atomic_json(path, record)
        with self.assertRaisesRegex(ValueError, 'size'):
            read_package(ROOT, path)
        with self.assertRaisesRegex(ValueError, 'immutable'):
            read_package(ROOT, rom)

    def test_device_selection_fails_before_open(self):
        bad = {**DEVICE, 'Status': 'Error'}
        for ports, selected in [([], 'COM92'), ([DEVICE, DEVICE], 'COM92'), ([bad], 'COM92'), ([DEVICE], None)]:
            self.args.uart_port = selected
            opener = unittest.mock.Mock()
            def discovery(folder, args):
                return select_uart(ports, args)
            with self.assertRaises((ValueError, RuntimeError)):
                with session(self.folder, self.args, self.folder / 'state', discover=discovery, opener=opener):
                    self.fail('invalid device reached open')
            opener.assert_not_called()

    def test_persistent_uncertainty_and_shared_device_lock(self):
        def discovery(folder, args):
            return select_uart([DEVICE], args)
        endpoint = Endpoint('timeout')
        opener = unittest.mock.Mock(return_value=endpoint)
        state = self.folder / 'state'
        with session(self.folder, self.args, state, discover=discovery, opener=opener) as (connection, seq, persist, _):
            with self.assertRaises(FileExistsError):
                with session(self.folder, self.args, state, discover=discovery, opener=opener):
                    pass
            with self.assertRaises(UncertainCompletion):
                Client(connection, sequence=seq, persist=persist).request('PING')
        self.assertTrue(endpoint.closed)
        with self.assertRaisesRegex(RuntimeError, 'uncertain'):
            with session(self.folder, self.args, state, discover=discovery, opener=opener):
                pass
        self.assertEqual(opener.call_count, 1)
        self.args.endpoint_restarted = True
        with session(self.folder, self.args, state, discover=discovery, opener=opener) as (_, seq, _, _):
            self.assertEqual(seq, 1)

    def test_builder_tagged_fake_session_and_failure_records(self):
        def fake_session(folder, args, state_root):
            return session(folder, args, self.folder / 'state',
                           discover=lambda folder, args: select_uart([DEVICE], args), opener=lambda port: Endpoint())
        tag = 'host-fixture-' + self.folder.name.rsplit(' ', 1)[-1].lower().replace('_', '-')
        with patch('n2m.host.command.session', fake_session), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['host', 'snapshot', '--uart-port', 'COM92', '--tag', tag, '--json'], ROOT), 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report['result']['snapshot']['size'], 5760)
        self.assertTrue(any(path.endswith('frame.2bpp') for path in report['artifacts']))
        self.assertTrue(any(path.endswith('transactions.jsonl') for path in report['artifacts']))
        for path, digest in report['artifacts'].items():
            self.assertEqual(file_hash(ROOT / path), digest)

    def test_cli_bad_package_fails_before_discovery_and_retains_reason(self):
        path, record = self.manifest()
        record['profile'] = 'unapproved-profile'
        atomic_json(path, record)
        with patch('n2m.host.command.session') as opener, redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['host', 'load', '--package', str(path), '--uart-port', 'COM92', '--json'], ROOT), 1)
        opener.assert_not_called()
        report = json.loads(stdout.getvalue())
        self.assertIn('profile', report['error'])
        self.assertTrue(any(name.endswith('transactions.jsonl') for name in report['artifacts']))

    def test_actual_packager_output_through_builder_load(self):
        packaged = build_target(ROOT, self.folder, SimpleNamespace(target='linker-basic', rebuild=True), {})
        self.assertEqual(packaged['status'], 'PASS', packaged.get('error'))
        manifest = (ROOT / packaged['rom']).parent / 'result.json'
        endpoint = Endpoint()
        def fake_session(folder, args, state_root):
            return session(folder, args, self.folder / 'state',
                           discover=lambda folder, args: select_uart([DEVICE], args), opener=lambda port: endpoint)
        with patch('n2m.host.command.session', fake_session), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['host', 'load', '--package', str(manifest), '--uart-port', 'COM92', '--json'], ROOT), 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report['result']['verified_bytes'], 32768)
        self.assertEqual(endpoint.rom, (ROOT / packaged['rom']).read_bytes())
        self.assertEqual(report['package']['rom_sha256'], packaged['artifacts'][packaged['rom']])

    def test_cli_zero_build_stops_before_product_commands(self):
        path, _ = self.manifest()
        for action in ('load', 'run', 'reset', 'halt', 'step', 'run-dots', 'input', 'snapshot'):
            with self.subTest(action=action):
                endpoint = Endpoint('zero-build')
                def fake_session(folder, args, state_root):
                    return session(folder, args, self.folder / 'state',
                                   discover=lambda folder, args: select_uart([DEVICE], args),
                                   opener=lambda port: endpoint)
                command = ['host', action, '--uart-port', 'COM92', '--json']
                if action == 'load':
                    command += ['--package', str(path)]
                if action in ('step', 'run-dots'):
                    command += ['--dots', '4']
                if action == 'input':
                    command += ['--mask', '255']
                with patch('n2m.host.command.session', fake_session), redirect_stdout(io.StringIO()) as stdout:
                    self.assertEqual(main(command, ROOT), 1)
                self.assertIn('build identity is zero', json.loads(stdout.getvalue())['error'])
                self.assertEqual([name for name, _, _ in endpoint.requests], ['PING'] + ['READ_HOST'] * 5)

    def test_serial_backend_configures_before_explicit_open(self):
        connection = unittest.mock.Mock()
        connection.dtr = True
        connection.rts = True
        def opening():
            self.assertEqual((connection.port, connection.dtr, connection.rts), ('COM92', False, False))
        connection.open.side_effect = opening
        module = SimpleNamespace(VERSION='3.5', EIGHTBITS=8, PARITY_NONE='N', STOPBITS_ONE=1,
                                 Serial=unittest.mock.Mock(return_value=connection))
        with patch.dict(sys.modules, {'serial': module}):
            self.assertIs(open_serial('COM92').connection, connection)
        self.assertEqual(module.Serial.call_args.kwargs['port'], None)
        self.assertEqual(module.Serial.call_args.kwargs['baudrate'], abi.WIRE_BAUD)
        self.assertEqual(module.Serial.call_args.kwargs['timeout'], 0)
        self.assertFalse(module.Serial.call_args.kwargs['xonxoff'])
        self.assertFalse(module.Serial.call_args.kwargs['rtscts'])
        self.assertFalse(module.Serial.call_args.kwargs['dsrdtr'])
        connection.open.assert_called_once()

    def test_serial_deadline_does_not_reconfigure_pending_write(self):
        class FixedPort(Endpoint):
            @property
            def timeout(self):
                return 0

            @timeout.setter
            def timeout(self, value):
                if hasattr(self, 'timeout_set'):
                    raise AssertionError('port reconfigured during exchange')
                self.timeout_set = True

        endpoint = FixedPort()
        transport = SerialTransport(endpoint)
        identity = Client(transport).identify()
        self.assertEqual(identity['abi'], abi.WIRE_ABI)
        self.assertEqual(len(endpoint.requests), 6)

    def test_serial_empty_reads_obey_short_deadline(self):
        now = [0.0]
        endpoint = unittest.mock.Mock()
        endpoint.read.return_value = b''
        sleeps = []
        def sleep(seconds):
            sleeps.append(seconds)
            now[0] += seconds
        transport = SerialTransport(endpoint, clock=lambda: now[0], sleep=sleep)
        transport.timeout = 0.0025
        self.assertEqual(transport.read(1), b'')
        self.assertAlmostEqual(now[0], 0.0025)
        self.assertTrue(all(0 < delay <= 0.001 for delay in sleeps))
        self.assertEqual(endpoint.read.call_count, 3)

    def test_serial_failure_remains_uncertain_without_replay(self):
        endpoint = unittest.mock.Mock()
        endpoint.write.side_effect = lambda packet: len(packet)
        endpoint.read.side_effect = OSError('read failed')
        client = Client(SerialTransport(endpoint))
        with self.assertRaises(UncertainCompletion):
            client.request('PING')
        with self.assertRaises(UncertainCompletion):
            client.request('PING')
        endpoint.write.assert_called_once()

    def test_serial_late_byte_is_not_accepted_or_replayed(self):
        now = [0.0]
        endpoint = unittest.mock.Mock()
        endpoint.write.side_effect = lambda packet: len(packet)
        def late_read(count):
            now[0] += 3
            return b'\0'
        endpoint.read.side_effect = late_read
        transport = SerialTransport(endpoint, clock=lambda: now[0])
        self.assertEqual(transport.read(1), b'')
        now[0] = 0.0
        endpoint.reset_mock()
        client = Client(transport, clock=lambda: now[0])
        with self.assertRaises(UncertainCompletion):
            client.request('PING')
        with self.assertRaises(UncertainCompletion):
            client.request('PING')
        endpoint.read.assert_called_once()
        endpoint.write.assert_called_once()

    def test_sequence_wrap_and_valid_error_clear_pending(self):
        endpoint = Endpoint()
        persisted = []
        client = Client(endpoint, sequence=0xffffffff, persist=lambda *args: persisted.append(args))
        client.request('PING')
        client.request('PING')
        with self.assertRaises(RejectedCommand):
            client.control('STEP', 1)
        self.assertEqual([seq for _, _, seq in endpoint.requests], [0xffffffff, 0, 1])
        self.assertEqual(persisted, [(0, True), (0, False), (1, True), (1, False), (2, True), (2, False)])



class SharedSessionRootTests(unittest.TestCase):
    def setUp(self):
        import subprocess
        (ROOT / 'workdir').mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='session-layout-', dir=ROOT / 'workdir')
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.primary, self.linked = base / 'primary repo', base / 'linked checkout'
        self.primary.mkdir()
        def git(*args):
            subprocess.run(['git', '-C', str(self.primary), *args], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        git('init')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '--allow-empty', '-m', 'fixture')
        git('worktree', 'add', '--detach', str(self.linked))
        self.expected = self.primary / 'workdir/host-sessions'
        self.args = SimpleNamespace(action='input', mask=0, tag='fixture', mode='observe',
            uart_port='COM92', uart_vid=None, uart_pid=None, uart_identity=None,
            endpoint_restarted=False, package='unused', wall_seconds=None,
            snapshot=False, image_stride=1, repeat=1)

    def invoke(self, kind, root, endpoint):
        from contextlib import nullcontext
        from n2m.host import command
        import springtrail_player
        opener = unittest.mock.Mock(return_value=endpoint)
        self.opener = opener
        def connection(folder, args, state_root):
            self.assertEqual(state_root, self.expected)
            return session(folder, args, state_root,
                           discover=lambda f, a: select_uart([DEVICE], a), opener=opener)
        if kind == 'command':
            with patch.object(command, 'session', connection):
                return command.run(root, root / 'workdir/builds/fixture', self.args, {})
        def run(client, *args, **kwargs):
            client.request('PING')
            return {'status': 'PASS'}
        with patch.object(springtrail_player, 'ROOT', root), \
             patch.object(springtrail_player, 'session', connection), \
             patch.object(springtrail_player.reader, 'bind_package', return_value=(b'', None)), \
             patch.object(springtrail_player, 'run', run), \
             patch('ci.storage.machine_lock', return_value=nullcontext()), redirect_stdout(io.StringIO()):
            return springtrail_player.worker(self.args)

    def test_primary_and_linked_entry_points_continue_one_sequence(self):
        for kind, root in (('command', self.primary), ('player', self.linked),
                           ('command', self.linked), ('player', self.primary)):
            endpoint = Endpoint()
            files = list(self.expected.glob('*.json'))
            previous = json.loads(files[0].read_text())['next_sequence'] if files else 0
            result = self.invoke(kind, root, endpoint)
            self.assertEqual(result['status'] if kind == 'command' else result,
                             'PASS' if kind == 'command' else 0)
            self.assertEqual(endpoint.requests[0][2], previous)
            current = json.loads(next(self.expected.glob('*.json')).read_text())
            self.assertEqual(current, {'next_sequence': previous + len(endpoint.requests), 'pending': False})
            self.assertTrue(endpoint.closed)

    def test_existing_uncertainty_blocks_both_entry_points_before_open(self):
        folder = self.primary / 'seed'
        folder.mkdir()
        with session(folder, self.args, self.expected,
                     discover=lambda f, a: select_uart([DEVICE], a),
                     opener=lambda p: Endpoint()) as (_wire, _seq, persist, _selected):
            persist(73, True)
        for kind, root in (('command', self.primary), ('player', self.linked)):
            endpoint = Endpoint()
            if kind == 'command':
                result = self.invoke(kind, root, endpoint)
                self.assertEqual(result['status'], 'FAIL')
                self.assertIn('uncertain', result['error'])
            else:
                with self.assertRaisesRegex(RuntimeError, 'uncertain'):
                    self.invoke(kind, root, endpoint)
            self.opener.assert_not_called()
            self.assertEqual(endpoint.requests, [])
        self.assertEqual(json.loads(next(self.expected.glob('*.json')).read_text()),
                         {'next_sequence': 73, 'pending': True})

    def test_no_git_repository_fails_without_fallback_store(self):
        import subprocess
        from n2m.host.transport import session_root
        import os
        with patch.dict(os.environ, {'GIT_CEILING_DIRECTORIES': str(Path(self.temporary.name).parent)}), \
             self.assertRaises(subprocess.CalledProcessError):
            session_root(Path(self.temporary.name))

if __name__ == '__main__':
    unittest.main()
