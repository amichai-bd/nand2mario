"""Project the selected original program's native events at actual fetch boundaries.

This adapter consumes only Core observations. The literal integration reference
is a separate diagnostic input, never a source of projected fields.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.n2m import generated_interfaces as abi
from tools.n2m.interface_codec import pack_record

# SM83 instruction sizes for the deliberately selected original program.
LENGTHS = {**dict.fromkeys((0x00,0x0B,0x22,0x76,0x78,0x79,0xAF,0xB1,0xD9,0xF1,0xF3,0xF5,0xFB),1),
           **dict.fromkeys((0x20,0x3E,0xC6,0xE0),2),
           **dict.fromkeys((0x01,0x21,0x31,0xC3,0xEA,0xFA),3)}
HEX = {'before','after','af','bc','de','hl','sp','ie','if','address','data'}


def fields(line):
    return {key:int(value,16 if key in HEX else 10)
            for key,value in (part.split('=') for part in line.split() if '=' in part)}


def project(log):
    scenario=json.loads((Path(__file__).parent/'scenario.json').read_text())
    if scenario['profile']!='dmg-direct-v1' or scenario['trace_version']!=abi.TRACE_VERSION or scenario['inputs']!=[{'completed_dot':0,'buttons':0}] or scenario['initializations']!=['LOAD_BEGIN','LOAD_END']:
        raise ValueError('unsupported declared lifecycle/input scenario')
    events, reads, fetches = [], {}, {}
    last_step=-1
    completed=set()
    for line in log.splitlines():
        if line.startswith(('event=','read ','fetch ')):
            item=fields(line); step=item.get('step',item.get('event'))
            if step<last_step or step in completed:
                raise ValueError('reordered native observation')
            last_step=step
            if line.startswith('event='): completed.add(step)
        if line.startswith('event='): events.append(fields(line))
        elif line.startswith('read '):
            item=fields(line); reads.setdefault(item['step'],[]).append(item)
        elif line.startswith('fetch '):
            item=fields(line); fetches.setdefault(item['step'],[]).append(item)
        elif line.startswith('closing '):
            raise ValueError('obsolete future closing observation')
    steps=set(range(len(events)))
    if set(reads)!=steps or set(fetches)!=steps:
        raise ValueError('missing/orphan native observations')
    result=[]
    for index,event in enumerate(events):
        if event['event'] != index: raise ValueError('missing/reordered native event')
        current=fetches[index]
        pattern=[f['kind'] for f in current]
        if pattern not in ([0],[1],[0,2]) or (event['halt']!=int(pattern==[0,2])):
            raise ValueError(f'unexpected fetch pattern at event {index}: {pattern}')
        if any(f['pending']!=4 for f in current) or any(a['native_dot']>=b['native_dot'] for a,b in zip(current,current[1:])):
            raise ValueError('invalid fetch timing')
        if any(a['dot']>b['dot'] for a,b in zip(reads[index],reads[index][1:])):
            raise ValueError('reordered native reads')
        irq=pattern==[1]
        expected_start=events[index-1]['dot'] if index else 4
        if current[0]['native_dot']!=expected_start or event['dot']<expected_start+4:
            raise ValueError('invalid initial fetch or actual event completion')
        if event['halt'] and current[-1]['native_dot']!=event['dot']:
            raise ValueError('HALT dummy fetch differs from actual completion')
        if event['buttons']!=0: raise ValueError('unsupported applied inputs')
        opcode=length=0
        if not irq:
            actual=reads[index]
            if actual[0]['address']!=event['before']:
                raise ValueError(f'first fetched address differs at event {index}')
            length=LENGTHS[actual[0]['data']]
            for byte in range(length):
                if actual[byte]['address'] != (event['before']+byte)&0xffff:
                    raise ValueError(f'nonsequential fetched operand at event {index}')
                opcode |= actual[byte]['data'] << (8*byte)
        record={'version':abi.TRACE_VERSION,'kind':abi.TRACE_INTERRUPT if irq else abi.TRACE_INSTRUCTION,'epoch':len(scenario['initializations']),'seq':index,
                'dot':event['dot'],
                'pc_before':event['before'],'pc_after':event['after'],
                'opcode':opcode,'opcode_length':length,'sp':event['sp'],
                'ime':event['ime'],'ime_delay':event['delay'],'halted':event['halt'],
                'stopped':event['stop'],'halt_bug':event['bug'],
                'ie':event['ie'],'iflags':event['if'],'buttons':event['buttons']}
        for pair in ('af','bc','de','hl'):
            record[pair[0]]=event[pair]>>8
            record[pair[1]]=event[pair]&255
        pack_record('retirement',record)
        result.append(record)
    return result


def compare(expected, actual):
    for index in range(max(len(expected),len(actual))):
        if index>=len(expected) or index>=len(actual):
            raise ValueError(f'event count at {index}: expected={len(expected)} actual={len(actual)}')
        if expected[index].keys()!=actual[index].keys():
            raise ValueError(f'event {index} field set differs')
        for key,value in expected[index].items():
            if value!=actual[index][key]:
                raise ValueError(f'event {index} {key}: expected={value} actual={actual[index][key]}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log',type=Path)
    parser.add_argument('reference',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    actual=project(args.log.read_text())
    args.output.write_text(json.dumps(actual,indent=2)+'\n')
    expected=[row['fields'] for row in json.loads(args.reference.read_text())]
    compare(expected,actual)
    print(f'PASS {len(actual)} complete retirement records against independent literal diagnostic; no DUT run')


if __name__=='__main__': main()
