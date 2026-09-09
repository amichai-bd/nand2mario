"""Byte-encoded bounded-run replies and fail-closed host completion."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.host.client import Client, UncertainCompletion
from n2m.interface_codec import decode_packet, encode_packet, pack_record, unpack_record


class Endpoint:
    def __init__(self, reason=0, executed=None):
        self.reason, self.executed = reason, executed
        self.buffer = bytearray()
        self.calls = 0

    def write(self, raw):
        header, payload = decode_packet(raw)
        assert header['command'] == 15
        requested = unpack_record('word', payload)['value']
        count = requested if self.executed is None else self.executed
        reply = pack_record('run_dots', dict(dot=0x100000000+count, executed=count, reason=self.reason))
        self.buffer.extend(encode_packet(header['seq'], 15, reply, kind=1))
        self.calls += 1
        return len(raw)

    def read(self, size):
        value = self.buffer[:size]
        del self.buffer[:size]
        return bytes(value)


class RunDots(unittest.TestCase):
    def test_exact_counts_and_stopped_result(self):
        for count in (1, 2, 70224):
            result = Client(Endpoint()).run_dots(count)
            self.assertEqual(result, dict(dot=0x100000000+count, executed=count, reason=0))
        for actual in (0, 3):
            result = Client(Endpoint(1, actual)).run_dots(10)
            self.assertEqual((result['executed'], result['reason']), (actual, 1))

    def test_invalid_counts_never_write(self):
        endpoint = Endpoint()
        for value in (0, -1, 70225, True, 1.5):
            with self.assertRaises(ValueError):
                Client(endpoint).run_dots(value)
        self.assertEqual(endpoint.calls, 0)

    def test_bad_completion_keeps_durable_uncertainty(self):
        for reason, executed in ((0, 3), (1, 4), (2, 0)):
            persisted = []
            endpoint = Endpoint(reason, executed)
            client = Client(endpoint, persist=lambda *row: persisted.append(row))
            with self.assertRaises(UncertainCompletion):
                client.run_dots(4)
            self.assertTrue(client.uncertain)
            self.assertTrue(persisted[-1][1])
            with self.assertRaises(UncertainCompletion):
                client.run_dots(4)
            self.assertEqual(endpoint.calls, 1)


if __name__ == '__main__':
    unittest.main()
