"""Original nonuniform OAM writes, live capture, and read-only post-HALT inspection."""
import json
from pathlib import Path
import cocotb
from cocotb.handle import Force, Release
from cocotb.triggers import Timer, ReadOnly, ValueChange, RisingEdge, FallingEdge
from cocotb.utils import get_sim_time
from test_integration import packet, requests, response, decode_record, known
from client_transport import frames


@cocotb.test(timeout_time=20, timeout_unit='ms')
async def late_write(dut):
    image=Path('program.gb').read_bytes()
    contract=json.loads(Path('late208.json').read_text())
    expected=contract['events']; counts={'records':0,'captures':0,'drain_edges':0}; replies=[]; accesses=[]; writes=[]
    with Path('transactions.jsonl').open('w') as trace, Path('retirement.csv').open('w') as records:
        records.write('seq,record\n')
        def log(kind, **values):
            trace.write(json.dumps(dict(kind=kind,time_ps=int(get_sim_time(unit='ps')),**values))+'\n');trace.flush()
        async def retirement():
            while True:
                await ValueChange(dut.record_event);await ReadOnly()
                raw=known(dut.record_sample);actual=decode_record(raw);i=counts['records']
                records.write(f'{i},{raw:096x}\n');records.flush()
                want=expected[i] if i<len(expected) else None
                log('retirement',expected=want,actual=actual)
                if actual['dot']==contract['access_retirement']:
                    boundary=next((item for item in accesses if item[0]==contract['access_commit']),None)
                    wanted=(4456,1,129)
                    assert boundary==wanted,f'LATE208_ACCESS expected={wanted} actual={boundary}'
                assert actual==want,f'LATE208_RECORD index={i} expected={want} actual={actual}'
                counts['records']+=1
        async def bus():
            while True:
                await ValueChange(dut.bus_event);await ReadOnly()
                raw=known(dut.bus_sample);data,write,address,dot=raw&255,(raw>>8)&1,(raw>>9)&65535,raw>>25
                if address==0xff40 and write:
                    writes.append((dot,data));log('lcdc',dot=dot,data=data)
                if address==contract['target']:
                    accesses.append((dot,write,data));log('oam',dot=dot,write=write,data=data)
        async def live_oam():
            # Sample 1 ns before the fixed40 ns system edge, before PPU capture.
            while True:
                await FallingEdge(dut.clk_sys);await Timer(19,unit='ns')
                if known(dut.reset_sys) or known(dut.core_reset):continue
                dot=known(dut.dot_count)
                if dot==4456 and known(dut.dut.late_busy):
                    sample=dict(dot=dot,address=known(dut.address),
                        destination=known(dut.dut.destination),pending=known(dut.dut.video_pending))
                    log('next_request',**sample)
                    store=next(event for event in expected if event['dot']==4460)
                    assert sample==dict(dot=4456,address=store['pc_after'],destination=0,pending=0)
                    counts['drain_edges']+=1
                if known(dut.gb_tick) and dot+1==4457:
                    sample=dict(pair=known(dut.dut.oam_pair_address),valid=known(dut.dut.oam_valid),
                        data=known(dut.dut.oam_data),capture=known(dut.dut.u_ppu.objects.capture_scan))
                    log('ppu_capture',dot=4457,**sample)
                    assert sample==dict(pair=78,valid=1,data=contract['oam'][156]|contract['oam'][157]<<8,capture=1),f'LATE208_CAPTURE {sample}'
                    counts['captures']+=1
        async def uart():
            async for encoded in frames(dut):
                decoded=response(encoded[:-1]);log('response',decoded=decoded)
                assert decoded[0]==len(replies),'LATE208_RESPONSE_SEQUENCE'
                replies.append(decoded)
        await Timer(1,unit='ns')
        tasks=[cocotb.start_soon(fn()) for fn in (retirement,bus,uart,live_oam)]
        await Timer(319,unit='ns');dut.reset_sys.value=0
        plan=list(requests(image))
        # Keep metadata/adoption intact, omit the historical150ms idle gap.
        plan[-2]=(8001000,plan[-2][1],plan[-2][2])
        plan[-1]=(8201000,plan[-1][1],plan[-1][2])
        plan.append((10501000,5,b'')) # Actual public HALT, after CPU HALT/LCD-off.
        for sequence,(when,command,payload) in enumerate(plan):
            await Timer(when*1000+1-int(get_sim_time(unit='ps')),unit='ps')
            if sequence==19:
                assert (known(dut.epoch),known(dut.dot_count),known(dut.paused))==(2,0,1)
            encoded=packet(sequence,command,payload)
            for index,byte in enumerate(encoded):
                for bit,value in enumerate([0,*[(byte>>n)&1 for n in range(8)],1]):
                    stamp=(when+40+index*3240+bit*320)*1000
                    await Timer(stamp-int(get_sim_time(unit='ps')),unit='ps');dut.uart_rx.value=value
        last=known(dut.dot_count)
        while known(dut.dot_count)<contract['halt_retirement']+16:
            await Timer(10,unit='us')
            current=known(dut.dot_count)
            log('progress',before=last,actual=current)
            assert current>last,'LATE208_PROGRESS'
            assert not known(dut.fault),'LATE208_OWNER_FAULT'
            last=current
        while not known(dut.paused) or len(replies)<22:
            await Timer(10,unit='us')
            assert not known(dut.fault),'LATE208_PAUSE_FAULT'
        assert counts==dict(records=624,captures=1,drain_edges=3),f'LATE208_LIVE_COUNTS {counts}'
        assert expected[-1]['halted']==1
        assert known(dut.dut.u_ppu.lcdc)==0,'LATE208_LCD_OFF'
        assert known(dut.dut.u_oam_late.phase)==0 and not known(dut.dut.late_busy)
        # Read-only DV inspection of the actual Intel A port, not UART readback.
        inspected=[]
        try:
            for pair in range(80):
                await FallingEdge(dut.clk_sys)
                dut.dut.u_stores.oam_request.value=Force((1<<25)|(pair<<16))
                await RisingEdge(dut.clk_sys);await ReadOnly()
                raw=known(dut.dut.u_stores.oam_response)
                log('inspection',pair=pair,response=raw)
                assert raw>>16==1,'LATE208_INSPECT_VALID'
                inspected.extend([raw&255,(raw>>8)&255])
        finally:
            await FallingEdge(dut.clk_sys)
            dut.dut.u_stores.oam_request.value=Release()
        assert inspected==contract['oam'],f'LATE208_FULL_OAM expected={contract["oam"]} actual={inspected}'
        for task in tasks:
            if task.done():task.result()
            task.cancel()
        want_access=[(event['dot']-4,1,event['a']) for event in expected
            if event['opcode']==0x12 and (event['d']<<8|event['e'])==contract['target']]
        want_writes=[(event['dot']-4,event['a']) for event in expected if event['opcode']==0x40e0]
        assert accesses==want_access,f'LATE208_BUS {accesses}'
        assert writes==want_writes,f'LATE208_WRITES {writes}'
        assert counts['records']==len(expected) and len(replies)==22,'LATE208_COMPLETION'
        log('complete',counts=counts,accesses=accesses,writes=writes)
    dut._log.info('PASS late208 complete CPU OAM write and full160 inspection')
