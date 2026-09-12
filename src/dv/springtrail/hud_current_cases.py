"""Thirty current publication operands; expected values come from original models."""
from dataclasses import replace
from entities_reference import World, initialize
from entities_cases import ADDRESSES, RANGES, state_bytes
from entities_frames import scene
from hud_reference import column, hud_tiles, progress_tiles
from blocks_reference import column_tiles
from movement_reference import STAGE_COLUMNS

CANARIES=(0xc09d,0xc1a0,0xc1ff,0xc227,0xc3ff,0xc4a0)


def cases():
    rows=[dict(name='paused-pair0',kind='restore',restore=0,mode=3)]
    rows += [dict(name=f'decode-{stage}-{index}',kind='decode',stage=stage,column=index)
             for stage,index in ((0,0),(0,95),(0,22),(0,31),(1,79),(2,79))]
    rows += [dict(name='used-item38',kind='decode',column=38,blocks=(1,0,0,0)),
             dict(name='broken-brick52',kind='decode',column=52,blocks=(0,2,0,0))]
    rows += [dict(name=f'camera-{stage}-{old}-{new}',kind='enter',stage=stage,old=old,camera=new)
             for stage,old,new in ((0,80,88),(0,88,96),(0,96,88),(0,607,608),
                                   (0,608,607),(0,96,96),(2,479,480),(2,480,479))]
    rows += [dict(name='final-pair30',kind='restore',restore=30,lcdc=0x51),
             dict(name='restart-twice',kind='restart',restore=14,old=144,level=1,lcdc=0x59),
             dict(name='dirty-defers-entering',kind='dirty',old=88,camera=96,dirty=39)]
    rows += [dict(name=f'hud-mode{mode}',kind='hud',mode=mode,score=mode%5) for mode in range(7)]
    rows += [dict(name=f'progress-map{bit}',kind='progress',lcdc=0x11|bit,stage=2)
             for bit in (0,8)]
    rows += [dict(name='scene-publication',kind='scene',old=88,camera=96,score=2,lcdc=0x19)]
    assert len(rows)==30
    return rows


def parts():
    rows=cases()
    return {chr(97+i):rows[i*6:(i+1)*6] for i in range(5)}


def world(case):
    w=initialize(World(mode=case.get('mode',1),stage=case.get('stage',0),score=case.get('score',0)))
    w=replace(w,player=replace(w.player,x=120*16,camera=case.get('camera',0)),
              blocks=case.get('blocks',w.blocks),block_dirty=case.get('dirty',0))
    if case['kind']=='progress':w=replace(w,lives=0x09,timer_high=3,timer_low=0x87)
    return w


def operands(case):
    data=dict(zip(ADDRESSES,state_bytes(world(case),new_level=case.get('level',0))))
    data.update({0xc023:case.get('old',0)//8,0xc02f:case.get('restore',32),
                 0xc051:0xa6,0xc052:0xa5,0xc053:0,0xc08f:0,
                 0xff40:case.get('lcdc',0x19 if case['kind']=='restart' else 0x11)})
    return data


def expected(case):
    w=world(case);writes=[]
    def put(a,v):writes.append((a,v))
    def decode(index,slot=0):
        writes.extend(enumerate(column(index,stage=w.stage),0xc200+16*slot))
        for y,tile in column_tiles(w.blocks,index+(0,96,176)[w.stage]).items():
            put(0xc200+16*slot+y-2,tile)
    def cache(indices):
        put(0xc053,0);put(0xc052,indices[0])
        for slot,index in enumerate(indices):decode(index,slot)
        put(0xc053,len(indices))
    def publish(indices):
        for index in indices:
            writes.extend((0x9c00+(y+2)*32+(index&31),v)
                          for y,v in enumerate(column(index,w.blocks,w.stage)))
    def hud(prepare=True,publish_values=True):
        values=hud_tiles(w)
        if prepare:writes.extend(enumerate(values,0xc220))
        if not publish_values:return
        for base in (0x9800,0x9c00):
            writes.extend((base+1+i,v) for i,v in enumerate(values[:6]));put(base+18,values[6])
    def progress(prepare=True,publish_values=True,base=None):
        values=progress_tiles(w);values=bytes(values[i] for i in (1,2,4,5,6,7))
        if prepare:writes.extend(enumerate(values,0xc097))
        if not publish_values:return
        if base is None:base=0x9c00 if case.get('lcdc',0x11)&8 else 0x9800
        writes.extend((base+32+x,v) for x,v in zip((2,3,13,14,15,18),values))
    def entering():
        old,new=case.get('old',0)//8,case.get('camera',0)//8
        index=new+20 if new>old else new
        return index if old!=new and index<STAGE_COLUMNS[w.stage] else None
    kind=case['kind']
    if kind=='decode':decode(case['column'])
    elif kind in ('restore','restart'):
        for _ in range(2 if kind=='restart' else 1):
            start=0 if kind=='restart' else case['restore'];ids=[start,start+1]
            if kind=='restart':
                put(0xc02f,0);put(0xc023,0);put(0xff40,operands(case)[0xff40]&~8)
            cache(ids)
            if start==30:hud(publish_values=False);progress(publish_values=False)
            publish(ids);put(0xc02f,start+2)
            if start==30:
                put(0xff40,operands(case)[0xff40]|8);hud(prepare=False);progress(prepare=False,base=0x9c00)
    elif kind=='hud':hud()
    elif kind=='progress':progress()
    elif kind=='dirty':
        cache([38,39]);put(0xc08f,2);put(0xc083,0);publish([38,39]);put(0xc08f,0)
        index=entering();cache([index]);publish([index]);put(0xc023,case['camera']//8)
    else:
        if kind=='scene':writes.extend(enumerate(scene(w),0xc100))
        index=entering()
        if index is None:put(0xc053,0)
        else:cache([index])
        # Prepare HUD/progress before publication in the combined case.
        if kind=='scene':
            values=hud_tiles(w);writes.extend(enumerate(values,0xc220))
            values=progress_tiles(w);writes.extend(enumerate(bytes(values[i] for i in (1,2,4,5,6,7)),0xc097))
        if index is not None:publish([index])
        put(0xc023,case['camera']//8)
        if kind=='scene':
            for base in (0x9800,0x9c00):
                values=hud_tiles(w);writes.extend((base+1+i,v) for i,v in enumerate(values[:6]));put(base+18,values[6])
            values=progress_tiles(w);writes.extend((0x9c20+x,values[i]) for x,i in zip((2,3,13,14,15,18),(1,2,4,5,6,7)))
            put(0xff46,0xc1);writes.extend(enumerate(scene(w),0xc400))
    return writes
