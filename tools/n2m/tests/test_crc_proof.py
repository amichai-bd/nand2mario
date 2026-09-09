"""Fixed diagnostic wire and durable-session failures, without serial access."""
from pathlib import Path
import sys
import unittest
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import generated_interfaces as abi
from n2m.host.client import Client
from n2m.host.crc_proof import run
from n2m.host.transport import SerialTransport
from n2m.host.command import run as command
from n2m.interface_codec import cobs_decode, decode_packet, encode_packet, pack_record, unpack_record


class Wire:
    def __init__(self, defect=None):
        self.defect, self.now, self.timeout = defect, 0, 2
        self.output = b''
        self.bad = None
        self.tokens = []
        self.sent = []

    def write(self, packet):
        self.sent.append(packet)
        try:
            header, payload = decode_packet(packet)
        except ValueError:
            self.bad = packet
            if self.defect == 'short':
                return len(packet) - 1
            if self.defect == 'bytes':
                self.output = b'\0'
            return len(packet)
        self.tokens.append(header['seq'])
        if header['command'] == abi.COMMAND_PING:
            if self.defect == 'timeout':
                return len(packet)
            value = 2 if self.defect == 'abi' else 1
        else:
            address = unpack_record('read_host', payload)['address']
            value = 0
            if address == abi.HOST_REG_STATE:
                value = abi.STATE_RUNNING if self.defect == 'running' else abi.STATE_PAUSED
            if address == abi.HOST_REG_DOT_LO:
                value = 19 + int(self.bad is not None and self.defect == 'drift')
            if address == abi.HOST_REG_RETIRE_LO:
                value = 7
        seq = header['seq'] + int(self.bad is not None and self.defect == 'sequence')
        self.output = encode_packet(seq, header['command'], pack_record('word', {'value': value}),
                                    kind=abi.WIRE_RESPONSE)
        return len(packet)

    def read(self, count):
        if self.output:
            result, self.output = self.output[:count], self.output[count:]
            return result
        self.now += self.timeout
        return b''

    def observe(self, seconds):
        self.timeout = seconds
        return self.read(1)


class CrcProofTests(unittest.TestCase):
    def client(self, defect=None):
        wire = Wire(defect)
        durable, events = [], []
        client = Client(wire, sequence=80, persist=lambda seq, pending: durable.append((seq, pending)),
                        clock=lambda: wire.now, record=events.append)
        return client, wire, durable, events

    def test_exact_corruption_and_recovery(self):
        client, wire, durable, events = self.client()
        result = run(client)
        seq = result['malformed_sequence']
        original = cobs_decode(encode_packet(seq, abi.COMMAND_PING)[:-1])
        damaged = cobs_decode(wire.bad[:-1])
        self.assertEqual(damaged[:-2], original[:-2])
        self.assertEqual(int.from_bytes(damaged[-2:], 'little') ^ int.from_bytes(original[-2:], 'little'), 1)
        self.assertEqual(wire.now, 2)
        self.assertEqual(result['before'], result['after'])
        self.assertIn(seq + 1, wire.tokens)
        reserved = durable.index((seq + 1, True))
        self.assertTrue(all(pending for _, pending in durable[reserved:-1]))
        self.assertFalse(durable[-1][1])
        self.assertEqual(events[-1]['event'], 'crc_proof_complete')

    def test_failures_stay_pending_without_retry(self):
        for defect in ('short', 'bytes', 'timeout', 'abi', 'sequence', 'drift'):
            with self.subTest(defect=defect):
                client, wire, durable, events = self.client(defect)
                with self.assertRaises(Exception):
                    run(client)
                self.assertTrue(durable[-1][1])
                self.assertEqual(sum(packet == wire.bad for packet in wire.sent), 1)
                self.assertNotIn('crc_proof_complete', [entry['event'] for entry in events])

    def test_running_precondition_sends_no_malformed_frame(self):
        client, wire, durable, _ = self.client('running')
        with self.assertRaises(ValueError):
            run(client)
        self.assertIsNone(wire.bad)
        self.assertFalse(durable[-1][1])

    def test_completion_journal_failure_keeps_pending(self):
        client, wire, durable, _ = self.client()
        def record(entry):
            if entry['event'] == 'crc_proof_complete':
                raise OSError('journal unavailable')
        client.record = record
        with self.assertRaises(OSError):
            run(client)
        self.assertTrue(durable[-1][1])

    def test_observation_keeps_boundary_bytes_and_waits_after_empty_reads(self):
        for edge in (False, True):
            with self.subTest(edge=edge):
                now, calls = [0.0], []
                class Connection:
                    def read(self, count):
                        calls.append(now[0])
                        if edge:
                            now[0] = 2.0
                            return b'\0'
                        return b''
                transport = SerialTransport(Connection(), clock=lambda: now[0],
                                            sleep=lambda delay: now.__setitem__(0, now[0] + delay))
                self.assertEqual(transport.observe(2), b'\0' if edge else b'')
                self.assertGreaterEqual(now[0], 2)
                if not edge:
                    self.assertGreater(len(calls), 1)

    def test_command_rejects_restart_or_bad_identity_before_open(self):
        for restarted, expected in ((True, '1' * 32), (False, 'bad')):
            with self.subTest(restarted=restarted), TemporaryDirectory() as tmp:
                root = Path(tmp)
                args = SimpleNamespace(action='crc-proof', endpoint_restarted=restarted,
                                       expected_build_id=expected)
                with patch('n2m.host.command.session') as session:
                    report = command(root, root, args, {})
                self.assertEqual(report['status'], 'FAIL')
                session.assert_not_called()

    def test_command_identity_mismatch_never_injects(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = SimpleNamespace(action='crc-proof', endpoint_restarted=False,
                                   expected_build_id='1' * 32)
            @contextmanager
            def session(*args):
                yield object(), 1, lambda *args: None, {}
            with patch('n2m.host.command.session', session), \
                    patch('n2m.host.command.subprocess.check_output', return_value=str(root / '.git')), \
                    patch('n2m.host.command.Client') as client, \
                    patch('n2m.host.crc_proof.run') as proof:
                client.return_value.identify.return_value = {'abi': 1, 'build_id': '2' * 32}
                report = command(root, root, args, {})
            self.assertEqual(report['status'], 'FAIL')
            proof.assert_not_called()


if __name__ == '__main__':
    unittest.main()
