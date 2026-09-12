"""Complete current scene shadows and bounded emitter protection.

Six cases in three two-call groups: ordinary/current changed poses, the actual
35-entry maximum with shot and release effect, reflected stomp/crack1, signed
fractional clipping, and a direct emitter call at DE=C1A0. The input ROM holds
ordinary state, poisoned shadow and canaries only; outputs stay in the oracle.
The C0FF terminal marker also rejects an immediate underflow write; C0FE and
C1A0 are preserved canaries around the shadow/marker boundary.

Per case285 seeded bytes at40 dots each plus dispatch fit13000. The42000
routine ceiling covers35pieces at620 dots, six courier table steps at296,
14entity table steps at300, ten pair steps at80, five effect/shot steps at100,
12signed projections at500,20tail bytes at52 and300selection dots:36316.
Two cases plus terminal fit111000, below160000; short56000 fits70000.
These are conservative source ceilings, not measured wall forecasts.
"""
from dataclasses import replace
from entities_reference import World, Entity
from entities_frames import scene
from entities_cases import ADDRESSES as STATE_ADDRESSES, RANGES as STATE_RANGES, state_bytes
from motion_reference import Player
from power_reference import Shot

ADDRESSES = STATE_ADDRESSES + list(range(0xc100,0xc1a0)) + [0xc0fe,0xc1a0]
RANGES = STATE_RANGES + ((0xc100,160),(0xc0fe,1),(0xc1a0,1))
SHORT=1
SHORT_BOUND=70000
FULL_BOUND=160000
ROUTINE_BOUND=42000
BUDGET=dict(cases_per_part=2,seed_and_dispatch=13000,routine_ceiling=42000,
            terminal=1000,conservative_total=111000,guard=160000)


def cases():
    normal=World(mode=1,player=Player(x=40*16,y=12*16),enemy_x=72*16,
                 curl=Entity(112*16,64*16),moving=Entity(32*16,80*16,1,0,16),
                 falling=Entity(112*16,104*16))
    changed=replace(normal,alive=False,stomp=8,curl=replace(normal.curl,state=1,timer=16),
                    falling=replace(normal.falling,state=1,timer=8))
    large=replace(normal,power=1,patrol_frame=8,shot=Shot(48*16,32*16,32,32,8),
                  effect_tile=124,effect_x=48*16,effect_y=48*16,effect_timer=8)
    flipped=replace(changed,stomp=16,enemy_vx=-8,
                    player=replace(changed.player,facing=32),
                    falling=replace(changed.falling,timer=16))
    clipped=replace(normal,player=replace(normal.player,x=1,camera=4),
                    enemy_x=1,curl=Entity(-5*16,16*16),
                    moving=Entity(160*16,140*16,1,0,16))
    rows=[]
    for name,w,kind in (('normal-scene',normal,'scene'),('changed-scene',changed,'scene'),
                        ('large-35-entries',large,'scene'),('flipped-stomp1-crack1',flipped,'scene'),
                        ('signed-clipped-scene',clipped,'scene'),('oam40-no-write',normal,'limit')):
        fields=state_bytes(w)
        before=fields+bytes([0xa5])*160+bytes((0x5a,0x69))
        shadow=scene(w) if kind=='scene' else bytes([0xa5])*160
        after=fields+shadow+bytes((0x5a,0x69))
        writes=[(0xc100+i,b) for i,b in enumerate(shadow)] if kind=='scene' else []
        rows.append(dict(name=name,kind=kind,before=before,after=after,writes=writes))
    return rows


def parts():
    rows=cases()
    return {'a':rows[:2],'b':rows[2:4],'c':rows[4:]}
