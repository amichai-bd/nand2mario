"""Fixed entity CPU operands and complete independent state snapshots."""
from dataclasses import replace
from entities_reference import World, Entity, initialize, update, spawn
from motion_reference import Player
from power_reference import PLAYING, PAUSED, RETRY, LARGE, HURT
from progress_reference import enter_stage
from blocks_cases import ADDRESSES as OLD_ADDRESSES, RANGES as OLD_RANGES, state_bytes as old_bytes

ADDRESSES = OLD_ADDRESSES + list(range(0xc090,0xc097)) + list(range(0xc300,0xc338))
RANGES = OLD_RANGES + ((0xc090,7),(0xc300,56))
SHORT = 1
SHORT_BOUND = 30000
FULL_BOUND = 160000
ROUTINE_BOUND = 24000
BUDGET = dict(cases_per_part=5, seed_and_dispatch=6000, routine_ceiling=24000,
              terminal=1000, conservative_total=151000, guard=160000)


def state_bytes(w, buttons=0, new_level=0):
    data = bytearray(old_bytes(w,buttons,new_level))
    data += bytes((w.lives,w.pending,w.timer_sub,w.timer_low,w.timer_high,w.expiring,w.stage))
    for e in (w.curl,w.moving,w.falling):
        data += e.x.to_bytes(2,'little',signed=True) + e.y.to_bytes(2,'little',signed=True)
        data += bytes((e.state,e.timer,e.vx&255)) + bytes(9)
    data += bytes((w.patrol_frame,w.stomp,w.rider)) + bytes(5)
    assert len(data)==len(ADDRESSES)
    return bytes(data)


def cases():
    result=[]
    base=World(mode=PLAYING,alive=False)
    def add(name,w,buttons=0,kind='game',level=0):
        after = (initialize(enter_stage(World(),buttons)) if kind=='reset'
                 else spawn(w,buttons)[0] if kind=='spawn' else update(w,buttons))
        entered = kind=='reset' or (after.mode==PLAYING and
                  (w.mode in (2,4,5,6) or (w.mode==PAUSED and buttons&64 and not w.previous&64)))
        out=buttons&~3 if after.crouch and kind=='game' else buttons
        result.append(dict(name=name,kind=kind,before=state_bytes(w,buttons,level),
                           after=state_bytes(after,out,1 if entered else level)))
    add('neutral-carry',replace(base,player=Player(x=184*16,y=96*16)))
    add('jump-off',replace(base,player=Player(x=184*16,y=96*16)),16)
    add('landing',replace(base,player=Player(x=184*16,y=95*16,jump=3,grounded=False)))
    add('right-edge-no-land',replace(base,player=Player(x=201*16,y=95*16,jump=3,grounded=False)))
    for name,x,v in (('moving-right',207,16),('moving-return',208,-16),('moving-left',176,-16)):
        add(name,replace(base,moving=Entity(x*16,112*16,1,0,v)))
    add('fall-arm',replace(base,player=Player(x=370*16,y=95*16,jump=3,grounded=False)))
    add('fall-delay',replace(base,falling=Entity(368*16,112*16,1,2)))
    add('fall-start',replace(base,falling=Entity(368*16,112*16,1,1)))
    add('fall-absent',replace(base,falling=Entity(368*16,142*16,2)))
    add('fall-stays-absent',replace(base,falling=Entity(368*16,144*16,3)))
    for name,x in (('curl-outside',295),('curl-range',296)):
        add(name,replace(base,player=Player(x=x*16,y=112*16)))
    add('curl-active-end',replace(base,curl=Entity(328*16,120*16,1,1)))
    add('curl-cooldown-end',replace(base,curl=Entity(328*16,120*16,0,1)))
    contact=replace(base,player=Player(x=328*16,y=112*16),curl=Entity(328*16,120*16,1,20))
    add('curl-small',contact)
    add('curl-large',replace(contact,power=LARGE))
    add('curl-protected',replace(contact,phase=HURT,phase_timer=20))
    add('curl-star',replace(contact,invincible=10))
    add('patrol-stomp',replace(base,alive=True,enemy_x=256*16,
                              player=Player(x=256*16,y=101*16,jump=3,grounded=False)))
    add('stomp-second-pose',replace(base,stomp=9))
    add('stomp-hidden',replace(base,stomp=1))
    add('patrol-endpoint',replace(base,alive=True,enemy_x=296*16-8))
    add('pause-freeze',replace(contact,mode=PAUSED))
    add('resume',replace(base,mode=PAUSED),128)
    add('select-reset',replace(contact,mode=PAUSED,stage=2),64)
    add('full-reset',replace(contact,stage=2,lives=0x17),0,'reset')
    for stage in (0,1):
        add('enter-stage'+str(stage+1),initialize(replace(base,stage=stage,mode=4)),128)
    add('invalid-slot',base,4,'spawn')
    add('live-curl-no-overwrite',base,1,'spawn')
    add('live-patrol-no-overwrite',replace(base,alive=True),0,'spawn')
    add('spawn-curl',replace(base,curl=Entity(328*16,120*16,2)),1,'spawn')
    add('spawn-falling',replace(base,falling=Entity(368*16,144*16,3)),3,'spawn')
    add('curl-stomp-immune',replace(contact,player=Player(x=328*16,y=101*16,jump=3,grounded=False)))
    from power_reference import Shot
    add('curl-shot-immune',replace(contact,phase=HURT,phase_timer=20,
                                   shot=Shot(327*16,120*16,16,0,20)))
    both=replace(base,alive=True,enemy_x=256*16,player=Player(x=256*16,y=112*16),
                 curl=Entity(256*16,120*16,1,20))
    add('patrol-stomp-before-curl',replace(both,player=Player(x=256*16,y=101*16,jump=3,grounded=False)))
    add('patrol-before-curl-fatal',both)
    add('rider-released-at-absence',replace(base,player=Player(x=370*16,y=126*16),
                                           falling=Entity(368*16,142*16,2)))
    return result


def parts():
    rows=cases()
    return {chr(97+i):rows[start:start+5] for i,start in enumerate(range(0,len(rows),5))}
