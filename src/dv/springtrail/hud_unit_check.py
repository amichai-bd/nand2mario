"""Ordered public CPU writes and actual OAM consumption for finite HUD cases."""
import json
from pathlib import Path
import sys
from hud_unit_cases import cases, expected, game, metadata, shadow
from interaction_cases import ADDRESSES, state_bytes

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools'))
from n2m.interface_codec import decode_record


class Check:
    def __init__(self, short=False):
        self.selected = cases()[:1] if short else cases()
        self.memory = {}; self.active = None; self.writes = []; self.reports = []
        self.durations = []; self.lines = 0; self.records = 0; self.last_dot = -1
        self.terminal = False; self.halted = False; self.ended = False
        self.triggers = []; self.dma = []

    def write(self, dot, address, data):
        assert not self.terminal, 'HUD_AFTER_TERMINAL'
        if address == 0xc0fc:
            assert self.active is None and data == len(self.reports)+1 and data <= len(self.selected), 'HUD_BEGIN'
            case = self.selected[data-1]
            assert bytes(self.memory.get(a, 0) for a in ADDRESSES) == state_bytes(game(case)), 'HUD_CALLER_STATE'
            assert self.memory.get(0xc051) == 0xa6, 'HUD_PUBLISHED_OPERAND'
            self.active = dot; self.writes = []
        elif address == 0xc0fd:
            assert self.active is not None and data == len(self.reports)+1, 'HUD_REPORT'
            case = self.selected[data-1]
            assert self.writes == expected(case), f'HUD_WRITES case={data} actual={self.writes} expected={expected(case)}'
            assert all(self.memory.get(a) == v for a, v in metadata(case).items()), 'HUD_METADATA'
            assert bytes(self.memory.get(a, 0) for a in ADDRESSES) == state_bytes(game(case)), 'HUD_RETURN_STATE'
            assert self.memory.get(0xc051) == 0xa6, 'HUD_PUBLISHED_MUTATION'
            self.durations.append(dot-self.active); self.reports.append(dot); self.active = None
        elif address == 0xc0ff:
            assert data == 0xa5 and self.active is None and len(self.reports) == len(self.selected), 'HUD_TERMINAL'
            self.terminal = True
        elif self.active is not None:
            assert address not in ADDRESSES and address != 0xc051, 'HUD_GAME_MUTATION'
            if (0xc100 <= address < 0xc1a0 or 0xc200 <= address < 0xc227
                    or 0xc300 <= address < 0xc3a0 or 0x8000 <= address < 0xa000
                    or 0xfe00 <= address < 0xfea0 or address in (0xff40, 0xff42, 0xff43, 0xff46)):
                self.writes.append((address, data))
            if address == 0xff46:
                assert self.selected[len(self.reports)]['kind'] == 'scene' and not self.triggers and data == 0xc1, 'HUD_DMA_TRIGGER'
                self.triggers.append(dot)
        self.memory[address] = data

    def line(self, text):
        assert not self.ended, 'HUD_AFTER_END'
        kind, raw = text.strip().split(' ')
        if kind == 'END':
            assert int(raw) == self.lines and self.terminal and self.halted and self.active is None, 'HUD_END'
            self.ended = True; return
        self.lines += 1
        value = int(raw, 16)
        if kind == 'W':
            self.write(value >> 24, (value >> 8) & 65535, value & 255)
        elif kind == 'R':
            row = decode_record(value)
            assert not self.halted and row['seq'] == self.records and row['epoch'] == 2 and not row['stopped'] and row['dot'] > self.last_dot, 'HUD_RETIRE'
            self.records += 1; self.last_dot = row['dot']
            if self.triggers and self.triggers[0] <= row['dot'] <= self.triggers[0]+644:
                assert 0xff80 <= row['pc_before'] < 0xff89, 'HUD_HRAM'
            if row['opcode'] == 0x76:
                assert self.terminal, 'HUD_EARLY_HALT'
                self.halted = True
        else:
            raise AssertionError('HUD_TRACE_KIND')

    def finish(self, pause):
        assert self.ended and self.terminal and self.halted and self.active is None, 'HUD_INCOMPLETE'
        assert len(self.reports) == len(self.selected), 'HUD_REPORT_COUNT'
        scenes = [case for case in self.selected if case['kind'] == 'scene']
        assert len(self.triggers) == len(scenes) and len(self.dma) == 160*len(scenes), 'HUD_DMA_COUNT'
        if scenes:
            for i, raw in enumerate(self.dma):
                assert (raw >> 18, (raw >> 8) & 255, raw & 255) == (self.triggers[0]+8+4*i, i, shadow(scenes[0])[i]), 'HUD_DMA_BYTE'
            assert pause > self.triggers[0]+644, 'HUD_DMA_PENDING'
        return dict(cases=len(self.reports), durations=self.durations, records=self.records,
                    lines=self.lines, dma_bytes=len(self.dma), pause=pause)


async def run(dut, short=False):
    import cocotb
    from cocotb.queue import Queue
    from cocotb.task import bridge
    from cocotb.triggers import Timer, ReadOnly, ValueChange
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
        async def dma():
            while True:
                await ValueChange(dut.dma_event); await ReadOnly()
                raw = known(dut.dma_sample)
                if (raw >> 16) & 1:
                    check.dma.append(raw); log('dma', raw=raw)
        def healthy():
            for task in tasks:
                if task.done(): task.result()
        await Timer(1, unit='ns')
        tasks = [cocotb.start_soon(f()) for f in (receive, dma)]
        try:
            await Timer(320, unit='ns'); dut.reset_sys.value = 0; dut.reset_pix.value = 0
            client = connect(dut, received, log, [])
            @bridge
            def load(): return client.identify(), adopt(client, verify(Path.cwd()))
            identity, loaded = await load(); log('load', identity=identity, loaded=loaded)
            assert (known(dut.epoch), known(dut.dot_count), known(dut.paused)) == (2, 0, 1), 'HUD_INITIAL'
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
                    assert prior < dot < (10000 if short else 120000) and not any(known(s) for s in (dut.fault, dut.paused, dut.reset_sys, dut.core_reset)), 'HUD_PROGRESS'
                    prior = dot
                refresh_clock(client); await control('HALT')
                await Timer(1, unit='ns'); await ReadOnly(); healthy()
                settled = (known(dut.dot_count), known(dut.record_sample), len(check.dma))
                assert known(dut.paused) and not known(dut.fault), 'HUD_PAUSE'
                await Timer(1, unit='us'); await ReadOnly(); healthy()
                assert (known(dut.dot_count), known(dut.record_sample), len(check.dma)) == settled and known(dut.paused), 'HUD_HOLD'
                assert not any(known(s) for s in (dut.fault, dut.reset_sys, dut.core_reset)), 'HUD_HOLD_FAULT'
                await Timer(1, unit='ns'); dut.public_trace_close.value = 1
                await Timer(100, unit='ns'); await ReadOnly(); healthy(); consume()
                summary = check.finish(settled[0])
                Path('summary.json').write_text(json.dumps(summary, indent=2)+'\n')
                log('complete', **summary)
        finally:
            for task in tasks: task.cancel()
    dut._log.info('PASS HUD unit complete')
