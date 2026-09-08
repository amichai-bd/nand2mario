"""Bounded original-program palette discriminator against independent Core."""
import json
from pathlib import Path
import sys
import cocotb
from cocotb.triggers import Timer, ReadOnly, ValueChange
from cocotb.utils import get_sim_time

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from src.dv.sameboy.retirement import project
from test_integration import packet,requests,response,decode_record,known
from client_transport import frames


@cocotb.test(timeout_time=210,timeout_unit='ms')
async def palette_contract(dut):
    image=Path('program.gb').read_bytes()
    native=Path('reference/observations.log').read_text()
    expected=project(native)
    assert len(expected)==10114 and expected[-2]['dot']==70912 and expected[-1]['dot']==70916
    visible=[]
    shades={0xffffff:0,0xaaaaaa:1,0x555555:2,0:3}
    for line in native.splitlines():
        if line.startswith('visible '):
            row=dict(part.split('=') for part in line.split()[1:])
            visible.append((int(row['frame']),int(row['y'])*160+int(row['x']),shades[int(row['rgb'],16)]))
    assert len(visible)==46080
    counts={'records':0,'pixels':0};replies=[];bgp=[]
    with Path('transactions.jsonl').open('w') as trace,Path('retirement.csv').open('w') as records,Path('pixels.csv').open('w') as pixels:
        records.write('seq,record\n');pixels.write('frame,index,dot,shade\n')
        def log(kind,**values):
            trace.write(json.dumps(dict(kind=kind,time_ps=int(get_sim_time(unit='ps')),**values))+'\n')
            trace.flush()
        async def retirement():
            while True:
                await ValueChange(dut.record_event);await ReadOnly()
                raw=known(dut.record_sample);actual=decode_record(raw);i=counts['records']
                records.write(f'{i},{raw:096x}\n')
                want=expected[i] if i<len(expected) else None
                log('retirement',expected=want,actual=actual)
                assert actual==want,f'PALETTE194_RECORD index={i} expected={want} actual={actual}'
                counts['records']+=1
        async def pixel():
            while True:
                await ValueChange(dut.pixel_event);await ReadOnly()
                raw=known(dut.pixel_sample)
                eligible,abort,start=raw&1,(raw>>1)&1,(raw>>2)&1
                shade,y,x=(raw>>3)&3,(raw>>5)&255,(raw>>13)&255
                epoch,dot=(raw>>21)&0xffffffff,raw>>53
                frame,index=divmod(counts['pixels'],23040)
                observed=(frame,index,shade);want=visible[counts['pixels']] if counts['pixels']<len(visible) else None
                pixels.write(f'{frame},{index},{dot},{shade}\n')
                log('pixel',expected=want,actual=observed,dot=dot,x=x,y=y)
                assert (x,y,epoch,start,abort,eligible)==(index%160,index//160,2,int(index==0),0,frame),'PALETTE194_ORDER'
                if frame==1:assert dot==70908+456*y+x,'PALETTE194_DUT_TIMING'
                assert observed==want,f'PALETTE194_PIXEL expected={want} actual={observed}'
                counts['pixels']+=1
        async def bus():
            while True:
                await ValueChange(dut.bus_event);await ReadOnly()
                raw=known(dut.bus_sample);data,write,address,dot=raw&255,(raw>>8)&1,(raw>>9)&65535,raw>>25
                if write and address==0xff47:
                    bgp.append((dot,data));log('bgp',dot=dot,data=data)
        async def uart():
            async for encoded in frames(dut):
                decoded=response(encoded[:-1]);log('response',decoded=decoded)
                assert decoded[0]==len(replies),'PALETTE194_RESPONSE_SEQUENCE'
                replies.append(decoded)
        await Timer(1,unit='ns')
        tasks=[cocotb.start_soon(fn()) for fn in (retirement,pixel,bus,uart)]
        await Timer(319,unit='ns');dut.reset_sys.value=0
        for sequence,(when,command,payload) in enumerate(requests(image)):
            await Timer(when*1000+1-int(get_sim_time(unit='ps')),unit='ps')
            if sequence==19:assert (known(dut.epoch),known(dut.dot_count),known(dut.paused))==(2,0,1)
            encoded=packet(sequence,command,payload)
            for index,byte in enumerate(encoded):
                for bit,value in enumerate([0,*[(byte>>n)&1 for n in range(8)],1]):
                    stamp=(when+40+index*3240+bit*320)*1000
                    await Timer(stamp-int(get_sim_time(unit='ps')),unit='ps');dut.uart_rx.value=value
        while known(dut.dot_count)<136280:
            await Timer(1,unit='us')
            assert not known(dut.fault),'PALETTE194_OWNER_FAULT'
        for task in tasks:
            if task.done():task.result()
            task.cancel()
        palette=json.loads(Path('image.json').read_text())
        assert counts=={'records':10114,'pixels':46080},f'PALETTE194_COUNTS {counts}'
        assert len(replies)==21 and bgp==[(356,0xe4),(70908,palette['palette'])],'PALETTE194_WRITE_BOUNDARY'
        log('complete',counts=counts,bgp=bgp,dot=known(dut.dot_count))
    dut._log.info('PASS palette194 records=10114 pixels=46080 write=70908')
