"""Two fixed frames, actual Intel memory, public source and RGB observations."""
import json
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly, Timer
from cocotb.utils import get_sim_time

from reference import EXPECTED_CRC, Raster, crc, frame
from public_trace import Trace


def known(handle):
    value = handle.value
    assert value.is_resolvable, f'VGA_CRC_UNKNOWN {handle._name}={value}'
    return int(value)


@cocotb.test()
async def vga_crc(dut):
    # Resolve every required public handle before the first stimulus.
    source = {name: getattr(dut, name) for name in
              ('source_valid', 'source_start', 'source_shade', 'source_dot', 'reset_sys')}
    journal = Path('transactions.jsonl').open('w', encoding='utf-8')
    def record(kind, **fields):
        journal.write(json.dumps({'kind': kind, 'time_ns': get_sim_time(unit='ns'), **fields}) + '\n')
        journal.flush()

    async def drive():
        for number, start_ns in enumerate((2000, 20_000_000)):
            await Timer(start_ns - get_sim_time(unit='ns'), unit='ns')
            applied = bytearray()
            for index, shade in enumerate(frame(number)):
                await FallingEdge(dut.clk_sys)
                source['source_valid'].value = 1
                source['source_start'].value = int(index == 0)
                source['source_shade'].value = shade
                source['source_dot'].value = number * 23040 + index
                await RisingEdge(dut.clk_sys)
                await ReadOnly()
                assert known(source['reset_sys']) == 0
                assert known(source['source_valid']) == 1
                assert known(source['source_start']) == int(index == 0)
                actual = known(source['source_shade'])
                assert actual == shade, f'VGA_CRC_SOURCE index={index}'
                applied.append(actual)
            await FallingEdge(dut.clk_sys)
            source['source_valid'].value = 0
            source['source_start'].value = 0
            assert len(applied) == 23040 and crc(applied) == EXPECTED_CRC[number]
            Path(f'source-{number}.bin').write_bytes(applied)
            record('source_complete', frame=number, count=len(applied), crc32=f'{crc(applied):08x}')

    driver = cocotb.start_soon(drive())
    model = Raster()
    trace = Trace()
    stream = None
    try:
        # One continuous simulator run. Transfer all passive samples every 2 ms.
        # The HDL closes the trace after the exact frozen observation window.
        for _ in range(26):
            await Timer(2, unit='ms')
            if stream is None:
                stream = Path('public-raster.txt').open(encoding='ascii')
            for timestamp, public in trace.feed(stream.read()):
                if public & (1 << 14):
                    assert trace.count <= 26 and model.edge == 0, 'VGA_CRC_RESET_ORDER'
                    continue
                assert trace.count > 26, 'VGA_CRC_EARLY_RESET_RELEASE'
                try:
                    complete = model.sample(public)
                except AssertionError as error:
                    record('mismatch', edge=model.edge, sample_time_ps=timestamp,
                           actual=public, message=str(error))
                    raise
                if complete:
                    record('output_complete', sample_time_ps=timestamp, **complete)
                if model.edge % 420000 == 0:
                    record('raster_progress', edge=model.edge, sample_time_ps=timestamp)
            if trace.ended:
                break
        trace.finish()
        await driver
        model.finish()
        for number, data in enumerate(model.canonical):
            assert data == Path(f'source-{number}.bin').read_bytes()
            Path(f'output-{number}.bin').write_bytes(data)
        summary = {'status': 'PASS', 'frames': 2, 'source_pixels': 46080,
                   'canonical_pixels': 46080, 'replicas': sum(model.replicas),
                   'raster_samples': model.edge, 'crc32': [f'{v:08x}' for v in EXPECTED_CRC]}
        Path('summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        record('complete', **summary)
        dut._log.info('PASS python-vga-crc')
    finally:
        if stream is not None:
            stream.close()
        if not driver.done():
            driver.cancel()
        journal.close()
