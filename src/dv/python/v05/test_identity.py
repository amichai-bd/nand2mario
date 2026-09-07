"""Read an independently chosen composition identity through actual UART pins."""
import json
from pathlib import Path
import sys

import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import Timer

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'src/dv/python/integration')]
from client_transport import connect, frames


@cocotb.test(timeout_time=20, timeout_unit='ms')
async def board_identity(dut):
    received = Queue()
    entries = []
    with Path('identity-transactions.jsonl').open('w') as trace:
        def observe(kind, **fields):
            trace.write(json.dumps(dict(kind=kind, **fields)) + '\n')

        async def receiver():
            async for encoded in frames(dut):
                received.put_nowait(encoded)

        task = cocotb.start_soon(receiver())
        try:
            await Timer(321, unit='ns')
            dut.reset_sys.value = 0
            dut.reset_pix.value = 0
            client = connect(dut, received, observe, entries)
            identity = await bridge(client.identify)()
            observe('identity', expected='0123456789abcdeffedcba9876543210', actual=identity)
            trace.flush()
            assert identity['build_id'] == '0123456789abcdeffedcba9876543210', 'V05_BOARD_IDENTITY'
            if task.done():
                task.result()
            Path('identity.json').write_text(json.dumps(identity, indent=2))
            dut._log.info('PASS V05 board identity')
        finally:
            task.cancel()
