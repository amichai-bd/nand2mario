"""The Verilator peer protocol against a fake access list; no simulator or cocotb."""
import asyncio
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src/dv/integration"))
from peer_bridge import Access, Bridge, LINE_SIZE, MAILBOX, read_line  # noqa: E402


class FakeAccess:
    """Mailboxes plus an endpoint that answers on the next advance."""

    def __init__(self, fault_busy=False):
        self.values = dict(tx_count=0, rx_count=0, tx_busy=0, rx_done=0, tx_go=0,
                           finish_request=0, simulation_ns=0, dot_count=0)
        self.arrays = {"tx_bytes": [0] * MAILBOX, "rx_bytes": [0] * MAILBOX}
        self.deposits = []
        self.fault_busy = fault_busy

    def observe(self, name, index=None):
        return self.arrays[name][index] if index is not None else self.values[name]

    def deposit(self, name, value, index=None):
        self.deposits.append((name, value, index))
        if index is not None:
            self.arrays[name][index] = value
        else:
            self.values[name] = value

    async def advance(self, microseconds=100):
        self.values["simulation_ns"] += microseconds * 1000
        self.values["dot_count"] += microseconds * 25
        if self.values["tx_go"]:
            self.values["tx_go"] = 0
            count = self.values["tx_count"]
            self.arrays["rx_bytes"][:count] = [b ^ 0x5A for b in self.arrays["tx_bytes"][:count]]
            self.arrays["rx_bytes"][count] = 0
            self.values["rx_count"] = count + 1
            self.values["rx_done"] = 1
            self.values["tx_busy"] = 1 if self.fault_busy else 0


class Channel:
    def __init__(self, lines):
        self.reader = io.BytesIO(b"".join(line + b"\n" for line in lines))
        self.sent = []
        self.closed = False

    def readline(self, size=-1):
        return self.reader.readline(size)

    def write(self, data):
        self.sent.append(data.decode("ascii").rstrip("\n"))

    def flush(self):
        pass

    def close(self):
        self.closed = True


def serve(lines, access=None, **options):
    access = access or FakeAccess()
    options.setdefault("waits", (136280,))
    clock = [0.0]
    bridge = Bridge(access, access.advance, clock=lambda: clock[0], **options)
    channel = Channel(lines)
    asyncio.run(bridge.serve(channel))
    return access, channel, bridge


class BridgeTests(unittest.TestCase):
    def test_transactions_wait_and_done_follow_the_retired_protocol(self):
        payload = bytes(range(1, 20))
        access, channel, bridge = serve([b"TX " + payload.hex().encode(), b"WAIT 136280", b"DONE"])
        expected = bytes(b ^ 0x5A for b in payload) + b"\0"
        self.assertEqual(channel.sent[0], f"RX 101000 {expected.hex()}")
        self.assertEqual(channel.sent[1].split()[0], "WAITED")
        self.assertGreaterEqual(access.values["dot_count"], 136280)
        self.assertTrue(channel.closed)
        self.assertEqual(access.values["finish_request"], 1)
        # The reply mailbox is cleared before the request is armed.
        armed = [d for d in access.deposits if d[0] in ("rx_count", "rx_done", "tx_go")]
        self.assertEqual(armed, [("rx_count", 0, None), ("rx_done", 0, None), ("tx_go", 1, None)])
        self.assertEqual(bridge.transactions[0]["reply"], expected.hex())

    def test_relative_wait_and_named_fail(self):
        access = FakeAccess()
        access.values["dot_count"] = 1000
        access, channel, _ = serve([b"WAIT 150000", b"DONE"], access, waits=(200000, 150000), relative=True)
        self.assertGreaterEqual(access.values["dot_count"], 151000)
        with self.assertRaisesRegex(RuntimeError, "^PLAY_OBJECT_COUNT$"):
            serve([b"FAIL PLAY_OBJECT_COUNT"], waits=(200000,), fail_prefix="PLAY_")
        # Without a declared prefix a FAIL line is an unknown message.
        with self.assertRaisesRegex(RuntimeError, "SMOKE_DRIVER_MESSAGE"):
            serve([b"FAIL PLAY_OBJECT_COUNT"])

    def test_protocol_faults_are_raised_by_name(self):
        cases = [([b"WAIT 5"], "SMOKE_DRIVER_WAIT_RANGE"),
                 ([b"HELLO"], "SMOKE_DRIVER_MESSAGE"),
                 ([b"TX 0"], "SMOKE_DRIVER_TX_SIZE"),
                 ([b"TX " + b"00" * (MAILBOX + 1)], "SMOKE_DRIVER_TX_SIZE"),
                 ([b"TX " + b"a" * (LINE_SIZE + 2)], "SMOKE_DRIVER_LINE_SIZE"),
                 ([], "SMOKE_DRIVER_PEER_EOF")]
        for lines, name in cases:
            with self.assertRaisesRegex(RuntimeError, name, msg=name):
                serve(lines)
        with self.assertRaisesRegex(RuntimeError, "SMOKE_DRIVER_RESPONSE_TIMEOUT"):
            access = FakeAccess(fault_busy=True)
            clock = [0.0]

            async def advance(microseconds=100):
                clock[0] += 61
                await access.advance(microseconds)

            bridge = Bridge(access, advance, waits=(1,), clock=lambda: clock[0])
            asyncio.run(bridge.serve(Channel([b"TX 01"])))

    def test_unterminated_line_and_access_outside_the_list(self):
        self.assertEqual(read_line(io.BytesIO(b"TX 01\n")), "TX 01")
        with self.assertRaisesRegex(RuntimeError, "SMOKE_DRIVER_LINE_SIZE"):
            read_line(io.BytesIO(b"TX 01"))

        class Top:
            tx_go = object()

        with self.assertRaisesRegex(RuntimeError, "SMOKE_DRIVER_ACCESS rx_done"):
            Access(Top(), ["tx_go", "rx_done"])
        with self.assertRaisesRegex(RuntimeError, "SMOKE_DRIVER_ACCESS dot_count"):
            Access(Top(), ["tx_go"]).handle("dot_count")

    def test_progress_lines_name_phase_ordinal_and_mailboxes(self):
        log = io.StringIO()
        _, _, bridge = serve([b"TX 01", b"DONE"], progress_log=log)
        lines = log.getvalue().splitlines()
        self.assertEqual([line.split()[1] for line in lines],
                         ["phase=received", "phase=prepared", "phase=response", "phase=extracted"])
        self.assertIn("ordinal=1 wall_ms=0 sim_ns=101000 dot=2525 tx_count=1 tx_busy=0 rx_count=2 rx_done=1", lines[2])
        self.assertEqual(bridge.ordinal, 1)


if __name__ == "__main__":
    unittest.main()
