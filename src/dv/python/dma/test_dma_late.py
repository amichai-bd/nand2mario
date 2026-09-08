"""Original image on the combined owner; no UART or loading acceptance claim."""
import json
from pathlib import Path
import cocotb
from cocotb.triggers import Timer, RisingEdge, FallingEdge, ValueChange, ReadOnly
from test_integration import decode_record, known

@cocotb.test(timeout_time=5, timeout_unit='ms')
async def late_write(dut):
    contract=json.loads(Path('late208.json').read_text())
    expected=contract['events']; actual=[]; captures=[]; accesses=[]
    for name in ('record_event','record_sample','inspection_enable','inspection_request',
                 'inspection_response','lcdc_observe','service_slot','capture_scan'):
        getattr(dut,name)
    with Path('retirement.csv').open('w') as records, Path('observations.jsonl').open('w') as trace:
        records.write('seq,record\n')
        def log(kind,**values):
            trace.write(json.dumps(dict(kind=kind,**values))+'\n');trace.flush()
        async def retirement():
            while True:
                await ValueChange(dut.record_event);await ReadOnly()
                raw=known(dut.record_sample);record=decode_record(raw);i=len(actual)
                want=expected[i] if i<len(expected) else None
                records.write(f'{i},{raw:096x}\n');records.flush();log('retirement',expected=want,actual=record)
                assert record==want,f'DMA_LATE_RECORD index={i} expected={want} actual={record}'
                actual.append(record)
        async def bus():
            while True:
                await ValueChange(dut.bus_event);await ReadOnly()
                raw=known(dut.bus_sample)
                data,write,address,dot=raw&255,(raw>>8)&1,(raw>>9)&65535,raw>>25
                if address==contract['target']:
                    accesses.append((dot,write,data));log('access',dot=dot,write=write,data=data)
        async def capture():
            while True:
                await FallingEdge(dut.clk_sys);await Timer(19,unit='ns')
                if known(dut.reset_sys):continue
                assert not (known(dut.fault) or known(dut.cpu_fault) or known(dut.ppu_fault)), 'DMA_LATE_PRODUCT_FAULT'
                if known(dut.gb_tick) and known(dut.dot_before)+1==4457:
                    sample=dict(pair=known(dut.ppu_oam_pair),valid=known(dut.ppu_oam_valid),
                        data=known(dut.ppu_oam_data),capture=known(dut.capture_scan))
                    log('capture',**sample)
                    want=dict(pair=78,valid=1,data=contract['oam'][156]|contract['oam'][157]<<8,capture=1)
                    assert sample==want,f'DMA_LATE_CAPTURE expected={want} actual={sample}'
                    captures.append(sample)
        async def progress():
            previous=0
            while True:
                await Timer(10,unit='us')
                if known(dut.run_enable) and not known(dut.cpu_halted):
                    now=known(dut.dot_before)
                    assert now>previous,f'DMA_LATE_PROGRESS previous={previous} actual={now}'
                    previous=now
        await Timer(1,unit='ns')
        tasks=[cocotb.start_soon(fn()) for fn in (retirement,bus,capture,progress)]
        await Timer(319,unit='ns');dut.reset_sys.value=0
        await RisingEdge(dut.memory_init_done)
        if not known(dut.cpu_initialized):await RisingEdge(dut.cpu_initialized)
        await FallingEdge(dut.clk_sys)
        assert known(dut.dot_before)==0 and known(dut.paused)==1
        Path('initial-state.json').write_text(json.dumps(dict(profile='direct',epoch=2,dot=0,
            mode='preloaded-execution',image_sha256=contract['sha256'],transport=False),indent=2)+'\n')
        dut.run_enable.value=1
        await RisingEdge(dut.cpu_halted)
        await FallingEdge(dut.clk_sys);dut.run_enable.value=0
        if not known(dut.paused):await RisingEdge(dut.paused)
        await Timer(2,unit='us')
        assert len(actual)==len(expected)==624,f'DMA_LATE_COUNT {len(actual)}'
        assert (4456,1,129) in accesses and len(captures)==1
        assert known(dut.lcdc_observe)==0 and known(dut.service_slot)==0
        dut.inspection_enable.value=1
        observed=[]
        try:
            for pair in range(80):
                await FallingEdge(dut.clk_sys);dut.inspection_request.value=(1<<25)|(pair<<16)
                await RisingEdge(dut.clk_sys);await Timer(1,unit='ns')
                raw=known(dut.inspection_response)
                assert raw>>16==1,f'DMA_LATE_INSPECTION_RESPONSE pair={pair}'
                observed.extend([raw&255,(raw>>8)&255])
        finally:
            await FallingEdge(dut.clk_sys);dut.inspection_request.value=0;dut.inspection_enable.value=0
        Path('oam.json').write_text(json.dumps(observed)+'\n')
        assert observed==contract['oam'],f'DMA_LATE_FULL_OAM expected={contract["oam"]} actual={observed}'
        Path('summary.json').write_text(json.dumps(dict(records=len(actual),bytes=len(observed),
            captures=len(captures),paused_dot=known(dut.dot_before),case=contract['case'],
            image_sha256=contract['sha256']),indent=2)+'\n')
        for task in tasks:task.cancel()
        print('PASS DMA late original CPU 624 records and full160 inspection')
