"""Current entity operands for the retained motion/power/block/progress suites.

Direct calls preserve their original literal expectations. Ordinary game calls
use the independent current world model, with every persistent field observed.
"""
from dataclasses import replace
from types import SimpleNamespace
import entities_cases as E
from entities_reference import World, Entity, initialize, update
from motion_reference import Player
from power_reference import Shot
from progress_reference import enter_stage


def decode(values, addresses, base=None):
    """Decode the fixture's explicit byte operands, never DUT output."""
    w=base or World(curl=Entity(328*16,120*16,2),
                   moving=Entity(176*16,112*16,3),falling=Entity(368*16,112*16,3))
    b=dict(zip(addresses,values))
    def byte(a,default):return b.get(a,default)
    def word(a,default,signed=False):
        if a not in b or a+1 not in b:return default
        n=b[a]|b[a+1]<<8
        return n-65536 if signed and n&32768 else n
    p=w.player
    p=replace(p,x=word(0xc010,p.x,True),y=word(0xc012,p.y,True),
              vx=word(0xc014,p.vx,True),vy=word(0xc016,p.vy,True),
              grounded=bool(byte(0xc018,p.grounded)),previous=byte(0xc01a,p.previous),
              camera=word(0xc01b,p.camera),fell=bool(byte(0xc01d,p.fell)),
              **{n:byte(0xc060+i,getattr(p,n)) for i,n in enumerate(
                 ('counter','direction','speed','phase','animation','pose','jump','index','saved','facing'))})
    s=w.shot
    signed8=lambda a,default: ((b[a]+128)%256-128) if a in b else default
    s=replace(s,x=word(0xc071,s.x,True),y=word(0xc073,s.y,True),
              vx=signed8(0xc075,s.vx),vy=signed8(0xc076,s.vy),ttl=byte(0xc077,s.ttl))
    fields=dict(player=p,shot=s,mode=byte(0xc000,w.mode),previous=byte(0xc024,w.previous),
                enemy_x=word(0xc026,w.enemy_x,True),enemy_vx=signed8(0xc028,w.enemy_vx),
                score=byte(0xc029,w.score),timer=word(0xc02a,w.timer),collected=byte(0xc02c,w.collected))
    for a,n in enumerate(('power','phase','phase_timer','invincible','throw','alive','crouch'),0xc06a):
        fields[n]=byte(a,getattr(w,n))
    fields['blocks']=tuple(byte(0xc078+i,v) for i,v in enumerate(w.blocks))
    for a,n in ((0xc07c,'coins'),(0xc07d,'effect_tile'),(0xc082,'effect_timer'),(0xc083,'block_dirty')):
        fields[n]=byte(a,getattr(w,n))
    fields['effect_x']=word(0xc07e,w.effect_x,True);fields['effect_y']=word(0xc080,w.effect_y,True)
    for a,n in enumerate(('lives','pending','timer_sub','timer_low','timer_high','expiring','stage'),0xc090):
        fields[n]=byte(a,getattr(w,n))
    return replace(w,**fields)


def adapt(suite):
    if getattr(suite,'__name__','').split('.')[-1] not in ('motion_cases','power_cases','blocks_cases','progress_cases'):
        return suite
    original=suite.cases()
    converted=[]
    for row in original:
        old=dict(zip(suite.ADDRESSES,row['before']))
        buttons=old[0xc019];level=old.get(0xc02e,0)
        before=decode(row['before'],suite.ADDRESSES)
        if row['kind']=='game':
            after=update(before,buttons)
            entered=after.mode==1 and (before.mode in (2,4,5,6) or
                (before.mode==3 and buttons&64 and not before.previous&64))
            after_level=1 if entered else level
            output=buttons&~3 if after.crouch else buttons
        elif row['kind']=='reset':
            after=initialize(enter_stage(World(),buttons));after_level=1;output=buttons
        else:
            # Preserve the previously frozen direct-call literal fields exactly;
            # new entity and unrelated fields must remain byte-identical.
            after=decode(row['after'],suite.ADDRESSES,before)
            old_after=dict(zip(suite.ADDRESSES,row['after']))
            after_level=old_after.get(0xc02e,level);output=old_after[0xc019]
        converted.append(dict(row,before=E.state_bytes(before,buttons,level),
                              after=E.state_bytes(after,output,after_level)))
    # Missing operands are constant defaults, stored once but CPU-written each call.
    missing=[a for a in E.ADDRESSES if a not in suite.ADDRESSES]
    indexes=[E.ADDRESSES.index(a) for a in missing]
    defaults=bytes(converted[0]['before'][i] for i in indexes)
    assert all(bytes(row['before'][i] for i in indexes)==defaults for row in converted)
    extra_ranges=[]
    for address in missing:
        if extra_ranges and extra_ranges[-1][0]+extra_ranges[-1][1]==address:
            start,count=extra_ranges[-1];extra_ranges[-1]=(start,count+1)
        else:extra_ranges.append((address,1))
    by_name={r['name']:r for r in converted}
    def parts():return {k:[by_name[r['name']] for r in rows] for k,rows in suite.parts().items()}
    return SimpleNamespace(ADDRESSES=E.ADDRESSES,RANGES=E.RANGES,cases=lambda:converted,
        SEED_RANGES=suite.RANGES,SEED_ADDRESSES=suite.ADDRESSES,
        EXTRA_RANGES=extra_ranges,EXTRA_VALUES=defaults,
        parts=parts,SHORT=getattr(suite,'SHORT',1),SHORT_BOUND=60000,
        FULL_BOUND=600000,ROUTINE_BOUND=24000,
        BUDGET=dict(seed_and_dispatch=6000,routine_ceiling=24000,guard=600000))
