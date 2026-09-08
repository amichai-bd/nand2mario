"""Actual CPU OAM read/write at the primary LCD-on +452-dot boundary."""
import json
from pathlib import Path
import cocotb
from cocotb.triggers import Timer, ReadOnly, ValueChange
from cocotb.utils import get_sim_time
from test_integration import packet, requests, response, decode_record, known
from client_transport import frames


@cocotb.test(timeout_time=20, timeout_unit='ms')
async def startup_access(dut):
    image=Path('program.gb').read_bytes()
    contract=json.loads(Path('startup202.json').read_text())
    expected=contract['events']; counts={'records':0}; replies=[]; accesses=[]; writes=[]
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
                assert actual==want,f'STARTUP202_RECORD index={i} expected={want} actual={actual}'
                counts['records']+=1
        async def bus():
            while True:
                await ValueChange(dut.bus_event);await ReadOnly()
                raw=known(dut.bus_sample);data,write,address,dot=raw&255,(raw>>8)&1,(raw>>9)&65535,raw>>25
                if address==0xff40 and write:
                    writes.append((dot,data));log('lcdc',dot=dot,data=data)
                if address==0xfe00:
                    accesses.append((dot,write,data));log('oam',dot=dot,write=write,data=data)
                    if dot==532:
                        want=(532,int(contract['case']=='write'),129 if contract['case']=='write' else 255)
                        assert accesses[-1]==want,f'STARTUP202_ACCESS expected={want} actual={accesses[-1]}'
        async def uart():
            async for encoded in frames(dut):
                decoded=response(encoded[:-1]);log('response',decoded=decoded)
                assert decoded[0]==len(replies),'STARTUP202_RESPONSE_SEQUENCE'
                replies.append(decoded)
        await Timer(1,unit='ns')
        tasks=[cocotb.start_soon(fn()) for fn in (retirement,bus,uart)]
        await Timer(319,unit='ns');dut.reset_sys.value=0
        plan=list(requests(image))
        # Keep metadata/adoption intact, omit the historical150ms idle gap.
        plan[-2]=(8001000,plan[-2][1],plan[-2][2])
        plan[-1]=(8201000,plan[-1][1],plan[-1][2])
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
            assert current>last,'STARTUP202_PROGRESS'
            assert not known(dut.fault),'STARTUP202_OWNER_FAULT'
            last=current
        for task in tasks:
            if task.done():task.result()
            task.cancel()
        want_access=[(60,1,0),(532,0,255)] if contract['case']=='read' else [(60,1,0),(532,1,129),(556,0,129)]
        want_writes=[(40,0),(80,129)] if contract['case']=='read' else [(40,0),(80,129),(548,0)]
        assert accesses==want_access,f'STARTUP202_BUS {accesses}'
        assert writes==want_writes,f'STARTUP202_WRITES {writes}'
        assert counts['records']==len(expected) and len(replies)==21,'STARTUP202_COMPLETION'
        log('complete',counts=counts,accesses=accesses,writes=writes)
    dut._log.info('PASS startup202 complete CPU OAM access at enable+452')
