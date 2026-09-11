"""Sample the DMG I/O registers over real UART pins while the core runs.

No pause, no step and no RAM access. The core is left in RUNNING for the whole
sample sequence, so the recorded values are live observations of a running
composition, correlated against the same host dot counter.
"""
import json
from pathlib import Path
import sys

import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import Timer
from cocotb.utils import get_sim_time

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'src/dv/python/integration')]
from client_transport import connect, frames
from n2m import generated_interfaces as abi
from n2m.preload import adopt, verify


def unpack(word):
    """The triple is one coherent edge: LY low, then STAT, then LCDC."""
    return dict(ly=word & 0xFF, stat=(word >> 8) & 0xFF, lcdc=(word >> 16) & 0xFF,
                mode=(word >> 8) & 0x3)


@cocotb.test(timeout_time=120, timeout_unit='ms')
async def io_registers(dut):
    samples = int(cocotb.plusargs.get('io_peek_samples', 200))
    received = Queue()
    entries = []
    with Path('transactions.jsonl').open('w') as trace:
        def observe(kind, **fields):
            trace.write(json.dumps(dict(kind=kind, time_ps=int(get_sim_time(unit='ps')), **fields)) + '\n')

        async def receiver():
            async for encoded in frames(dut):
                received.put_nowait(encoded)

        task = cocotb.start_soon(receiver())
        try:
            await Timer(321, unit='ns')
            dut.reset_sys.value = 0
            dut.reset_pix.value = 0
            client = connect(dut, received, observe, entries)

            @bridge
            def session():
                client.identify()
                adopt(client, verify(Path.cwd()))
                client.control('RUN')
                rows = []
                for index in range(samples):
                    row = unpack(client.read_host(abi.HOST_REG_IO_LCD_STATUS))
                    if index % 20 == 0 or index == samples - 1:
                        row['state'] = client.read_host(abi.HOST_REG_STATE)
                        row['dot'] = client.read_host(abi.HOST_REG_DOT_LO)
                        row['div'] = client.read_host(abi.HOST_REG_IO_DIV)
                        row['tima'] = client.read_host(abi.HOST_REG_IO_TIMA)
                        row['iflags'] = client.read_host(abi.HOST_REG_IO_IF)
                        row['ie'] = client.read_host(abi.HOST_REG_IO_IE)
                        row['ly_single'] = client.read_host(abi.HOST_REG_IO_LY)
                        row['stat_single'] = client.read_host(abi.HOST_REG_IO_STAT)
                    rows.append(row)
                client.control('HALT')
                return rows

            rows = await session()
            for index, row in enumerate(rows):
                observe('io_sample', index=index, **row)
            trace.flush()
            if task.done():
                task.result()

            full = [row for row in rows if 'state' in row]
            # Reading never pauses: the endpoint stayed RUNNING throughout.
            assert all(row['state'] == abi.STATE_RUNNING for row in full), 'IO_PEEK_NOT_RUNNING'
            dots = [row['dot'] for row in full]
            assert all(b > a for a, b in zip(dots, dots[1:])), 'IO_PEEK_DOTS_STALLED'
            # Reserved bits stay clear, so the committed view is what is reported.
            assert all(row['stat'] < 0x80 for row in rows), 'IO_PEEK_STAT_BIT7'
            assert all(row['iflags'] < 0x20 and row['ie'] < 0x100 for row in full), 'IO_PEEK_IF_RANGE'
            assert all(row['ly'] <= 153 for row in rows), 'IO_PEEK_LY_RANGE'
            lit = [row for row in rows if row['lcdc'] & 0x80]
            assert lit, 'IO_PEEK_LCD_NEVER_ENABLED'
            # Mode progression. VBlank is mode 1 on lines 144 through 153, and
            # readable LY wraps to 0 early during line 153 while the PPU is
            # still in VBlank, so mode 1 with LY 0 is correct DMG behavior
            # observed on the board. Lines 1 through 143 are never VBlank.
            for row in lit:
                if row['mode'] == 1:
                    ok = row['ly'] >= 144 or row['ly'] == 0
                else:
                    ok = row['ly'] < 144
                assert ok, f"IO_PEEK_MODE_PROGRESSION ly={row['ly']} stat={row['stat']:02x}"
            lines = {row['ly'] for row in lit}
            assert len(lines) >= 20, f'IO_PEEK_LY_PROGRESS lines={len(lines)}'
            # Simulation covers scanline progression within the wall budget.
            # Whole-frame coverage including VBlank belongs to the board session.
            assert max(lines) >= 60, f'IO_PEEK_LY_REACH max={max(lines)}'
            assert len({row['div'] for row in full}) >= 4, 'IO_PEEK_DIV_STALLED'
            Path('io_samples.json').write_text(json.dumps(rows, indent=2))
            dut._log.info(f'PASS io peek live samples={len(rows)} lines={len(lines)}')
        finally:
            task.cancel()
