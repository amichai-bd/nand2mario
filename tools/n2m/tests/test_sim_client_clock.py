"""Client deadlines across simulated idle time, without a licensed simulator."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from n2m import generated_interfaces as abi
from n2m.host.client import Client, UncertainCompletion
from n2m.interface_codec import decode_packet, encode_packet, pack_record


class ClockTests(unittest.TestCase):
    def test_idle_refresh_preserves_real_deadline(self):
        task, triggers, utils = (ModuleType('task'), ModuleType('triggers'), ModuleType('utils'))
        task.bridge = task.resume = lambda fn: fn
        for name in ('FallingEdge', 'ReadOnly', 'Timer', 'with_timeout'):
            setattr(triggers, name, None)
        now = [4.0]
        utils.get_sim_time = lambda **kwargs: now[0]
        modules = {'cocotb': ModuleType('cocotb'), 'cocotb.task': task,
                   'cocotb.triggers': triggers, 'cocotb.utils': utils}
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('clock_transport',
                ROOT / 'src/dv/python/integration/client_transport.py')
            adapter = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(adapter)

        class Reply:
            sim_time = 0.0

            def __init__(self, latency):
                self.latency = latency

            def write(self, packet):
                header, _ = decode_packet(packet)
                self.pending = bytearray(encode_packet(header['seq'], header['command'],
                    pack_record('dot', {'dot': 42312068}), kind=abi.WIRE_RESPONSE))
                self.sim_time = now[0] + self.latency
                return len(packet)

            def read(self, count):
                assert count == 1
                return bytes([self.pending.pop(0)])

        # Four seconds of idle time exceeds the two-second reply deadline.
        stale = Reply(0.001)
        client = Client(stale, clock=lambda: stale.sim_time)
        with self.assertRaisesRegex(UncertainCompletion, 'response timeout'):
            client.control('HALT')

        current = Reply(0.001)
        client = Client(current, clock=lambda: current.sim_time)
        adapter.refresh_clock(client)
        self.assertEqual(client.control('HALT'), {'dot': 42312068})

        late = Reply(2.001)
        client = Client(late, clock=lambda: late.sim_time)
        adapter.refresh_clock(client)
        with self.assertRaisesRegex(UncertainCompletion, 'response timeout'):
            client.control('HALT')


if __name__ == '__main__':
    unittest.main()
