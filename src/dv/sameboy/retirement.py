"""Project the selected original program's native events at actual fetch boundaries.

This adapter consumes only Core observations. The literal integration reference
is a separate diagnostic input, never a source of projected fields.
"""
import argparse
import json
from pathlib import Path

# SM83 instruction sizes for the deliberately selected original program.
LENGTHS = {**dict.fromkeys((0x00,0x22,0x76,0x78,0x79,0xAF,0xD9,0xF1,0xF3,0xF5,0xFB),1),
           **dict.fromkeys((0x3E,0xC6,0xE0),2),
           **dict.fromkeys((0x01,0x21,0x31,0xC3,0xEA,0xFA),3)}
HEX = {'before','after','af','bc','de','hl','sp','ie','if','address','data'}


def fields(line):
    return {key:int(value,16 if key in HEX else 10)
            for key,value in (part.split('=') for part in line.split() if '=' in part)}


def project(log):
    events, reads, fetches = [], {}, {}
    for line in log.splitlines():
        if line.startswith('event='): events.append(fields(line))
        elif line.startswith('read '):
            item=fields(line); reads.setdefault(item['step'],[]).append(item)
        elif line.startswith('fetch '):
            item=fields(line); fetches.setdefault(item['step'],[]).append(item)
    result=[]
    for index,event in enumerate(events):
        if event['event'] != index: raise ValueError('missing/reordered native event')
        current=fetches[index]
        irq=current[0]['kind']==1
        if event['halt']:
            closing=[f for f in current if f['kind']==2]
        else:
            closing=fetches.get(index+1,[])[:1]
        if len(closing)!=1 or closing[0]['pending']!=4:
            raise ValueError(f'missing four-dot final fetch at event {index}')
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
        record={'version':1,'kind':int(irq),'epoch':2,'seq':index,
                'dot':closing[0]['native_dot']+closing[0]['pending'],
                'pc_before':event['before'],'pc_after':event['after'],
                'opcode':opcode,'opcode_length':length,'sp':event['sp'],
                'ime':event['ime'],'ime_delay':event['delay'],'halted':event['halt'],
                'stopped':event['stop'],'halt_bug':event['bug'],
                'ie':event['ie'],'iflags':event['if'],'buttons':0}
        for pair in ('af','bc','de','hl'):
            record[pair[0]]=event[pair]>>8
            record[pair[1]]=event[pair]&255
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
