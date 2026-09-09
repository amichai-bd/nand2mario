"""Frozen software operands; expected results are calculated before DUT runs."""
from dataclasses import replace
from movement_reference import Player,step,world_tile


def timing_marker(begin,elapsed,address,dot,data,buttons):
    """One measured call must precede each software report."""
    if address==0xc0ee:
        assert begin is None and elapsed is None and data==buttons,'MOVEMENT_BEGIN'
        return dot,None
    assert address==0xc0ef and begin is not None and elapsed is None and data==0,'MOVEMENT_END'
    elapsed=dot-begin
    assert 0<elapsed<4200,'MOVEMENT_VBLANK_BUDGET'
    return None,elapsed


def timing_report(begin,elapsed):
    assert begin is None and elapsed is not None,'MOVEMENT_REPORT_TIMING'
    return elapsed


def groups():
    return [
        ('walk-run-opposed',Player(),[1,33,35,2,0]),
        ('jump-held',Player(),[16]*45+[0,16]),
        ('gap-fall',Player(x=184*16,camera=112),[0]*20),
        ('side-right',Player(x=71*16,y=88*16,grounded=False),[33]),
        ('side-left',Player(x=121*16,y=88*16,grounded=False,camera=49),[34]),
        ('head',Player(x=80*16,y=105*16,vy=-32,grounded=False,camera=8),[0]),
        ('landing',Player(x=80*16,y=79*16,vy=32,grounded=False,camera=8),[0]),
        ('left-bound',Player(x=0),[34]),
        ('right-bound',Player(x=760*16,camera=608),[33]),
        ('camera-anchor',Player(x=72*16),[33]),
        ('camera-tile',Player(x=78*16,camera=6),[33]),
        ('camera-wrap',Player(x=326*16,camera=254),[33]),
        ('camera-limit',Player(x=678*16,camera=606),[33]),
        ('fraction-side',Player(x=71*16+8,y=88*16,grounded=False),[33]),
        ('fraction-land',Player(x=80*16+8,y=79*16+8,vy=32,grounded=False,camera=8),[0]),
        # Reachable fourth jump update: three horizontal rows and two vertical
        # columns, with a new camera tile on the same normal frame.
        ('camera-air-corner',Player(x=2544,y=1564,vx=32,vy=-72,grounded=False,previous=33,camera=87),[33])]


def packed(player,buttons):
    data=b''.join((value&65535).to_bytes(2,'little') for value in (player.x,player.y,player.vx,player.vy))
    return data+bytes((player.grounded,buttons,player.previous))+player.camera.to_bytes(2,'little')+bytes((player.fell,))


def expected():
    rows=[]
    for name,initial,buttons in groups():
        state=initial
        for value in buttons:
            before=state
            state=step(state,value)
            writes=[]
            if len(buttons)==1:
                old,new=before.camera//8,state.camera//8
                if new!=old:
                    column=new+20 if new>old else new
                    if column<96:
                        writes += [(0x9800+(column&31)+32*y,world_tile(column,y)) for y in range(18)]
                writes += [(0xff43,state.camera&255),(0xfe00,0 if state.fell else state.y//16+16),
                           (0xfe01,state.x//16-state.camera+8),(0xfe02,12),(0xfe03,0)]
            rows.append(dict(group=name,buttons=value,bytes=packed(state,value).hex(),writes=writes))
    return rows
