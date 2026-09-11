"""Complete motion snapshots from actual CPU writes and ordered markers."""
import json
from pathlib import Path
import sys
from motion_cases import ADDRESSES, cases

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools'))
from n2m.interface_codec import decode_record


class Check:
    def __init__(self, short=False):
        self.selected = cases()[:1] if short else cases()
        self.memory = {}; self.active = None; self.reports = []; self.durations = []
        self.lines = 0; self.records = 0; self.last_dot = -1
        self.terminal = False; self.halted = False; self.ended = False

    def snapshot(self):
        assert all(a in self.memory for a in ADDRESSES), 'MOTION_UNINITIALIZED'
        return bytes(self.memory[a] for a in ADDRESSES)

    def write(self, dot, address, data):
        assert not self.terminal, 'MOTION_AFTER_TERMINAL'
        assert not (0x8000 <= address < 0xa000 or 0xfe00 <= address < 0xfea0
                    or address in (0xff42, 0xff43, 0xff46)), 'MOTION_DISPLAY_WRITE'
        if address == 0xff40:
            assert not data and self.active is None and not self.reports, 'MOTION_LCD'
        if address == 0xc0fc:
            assert self.active is None and data == len(self.reports)+1 and data <= len(self.selected), 'MOTION_BEGIN'
            assert self.snapshot() == self.selected[data-1]['before'], 'MOTION_OPERANDS'
            self.active = dot
        elif address == 0xc0fd:
            assert self.active is not None and data == len(self.reports)+1, 'MOTION_REPORT'
            case = self.selected[data-1]
            actual = self.snapshot()
            assert actual == case['after'], f'MOTION_STATE {case["name"]} actual={actual.hex()} expected={case["after"].hex()}'
            duration = dot-self.active
            assert 0 < duration <= (20000 if case['kind'] == 'game' else 8000), 'MOTION_ROUTINE_BOUND'
            self.durations.append(duration)
            self.reports.append(dict(name=case['name'], dot=dot, state=actual.hex()))
            self.active = None
        elif address == 0xc0ff:
            assert data == 0xa5 and self.active is None and len(self.reports) == len(self.selected), 'MOTION_TERMINAL'
            self.terminal = True
        self.memory[address] = data

    def line(self, text):
        assert not self.ended, 'MOTION_AFTER_END'
        kind, raw = text.strip().split(' ')
        if kind == 'END':
            assert int(raw) == self.lines and self.terminal and self.halted and self.active is None, 'MOTION_END'
            self.ended = True
            return
        self.lines += 1
        value = int(raw, 16)
        if kind == 'W':
            self.write(value >> 24, (value >> 8) & 65535, value & 255)
        elif kind == 'R':
            row = decode_record(value)
            assert not self.halted and row['seq'] == self.records and row['epoch'] == 2 and not row['stopped'] and row['dot'] > self.last_dot, 'MOTION_RETIRE'
            self.records += 1; self.last_dot = row['dot']
            if row['opcode'] == 0x76:
                assert self.terminal, 'MOTION_EARLY_HALT'
                self.halted = True
        else:
            raise AssertionError('MOTION_TRACE_KIND')

    def finish(self, pause):
        assert self.ended and self.terminal and self.halted and self.active is None, 'MOTION_INCOMPLETE'
        assert len(self.reports) == len(self.selected) and pause > self.last_dot, 'MOTION_COMPLETE'
        return dict(cases=len(self.reports), reports=self.reports, durations=self.durations,
                    records=self.records, lines=self.lines, pause=pause)


async def run(dut, short=False):
    import cocotb
    from cocotb.queue import Queue
    from cocotb.task import bridge
    from cocotb.triggers import Timer, ReadOnly
    sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'src/dv/python/integration')]
    from client_transport import connect, frames, refresh_clock
    from test_integration import known
    from n2m.preload import adopt, verify
    check = Check(short); received = Queue(); tasks = []
    with Path('transactions.jsonl').open('w') as journal:
        def log(kind, **values):
            journal.write(json.dumps(dict(kind=kind, **values))+'\n'); journal.flush()
        async def receive():
            async for frame in frames(dut): received.put_nowait(frame)
        def healthy():
            for task in tasks:
                if task.done(): task.result()
        await Timer(1, unit='ns')
        tasks = [cocotb.start_soon(f()) for f in (receive,)]
        try:
            await Timer(320, unit='ns'); dut.reset_sys.value = 0; dut.reset_pix.value = 0
            client = connect(dut, received, log, [])
            @bridge
            def load(): return client.identify(), adopt(client, verify(Path.cwd()))
            identity, loaded = await load(); log('load', identity=identity, loaded=loaded)
            assert (known(dut.epoch), known(dut.dot_count), known(dut.paused)) == (2, 0, 1), 'MOTION_INITIAL'
            @bridge
            def control(action): return client.control(action)
            with Path('springtrail.trace').open() as trace:
                def consume():
                    while True:
                        offset = trace.tell(); line = trace.readline()
                        if not line or not line.endswith('\n'):
                            trace.seek(offset); return
                        check.line(line)
                refresh_clock(client); await control('RUN')
                prior = 0
                while not check.halted:
                    await Timer(10, unit='us'); await ReadOnly(); healthy(); consume()
                    dot = known(dut.dot_count)
                    assert prior < dot < (10000 if short else 500000) and not any(known(s) for s in (dut.fault, dut.paused, dut.reset_sys, dut.core_reset)), 'MOTION_PROGRESS'
                    prior = dot
                refresh_clock(client); await control('HALT')
                await Timer(1, unit='ns'); await ReadOnly(); healthy()
                settled = (known(dut.dot_count), known(dut.record_sample))
                assert known(dut.paused) and not known(dut.fault), 'MOTION_PAUSE'
                await Timer(1, unit='us'); await ReadOnly(); healthy()
                assert (known(dut.dot_count), known(dut.record_sample)) == settled and known(dut.paused), 'MOTION_HOLD'
                assert not any(known(s) for s in (dut.fault, dut.reset_sys, dut.core_reset)), 'MOTION_HOLD_FAULT'
                await Timer(1, unit='ns'); dut.public_trace_close.value = 1
                await Timer(100, unit='ns'); await ReadOnly(); healthy(); consume()
                summary = check.finish(settled[0])
                Path('summary.json').write_text(json.dumps(summary, indent=2)+'\n')
                log('complete', **summary)
        finally:
            for task in tasks: task.cancel()
    dut._log.info('PASS MOTION unit complete')
