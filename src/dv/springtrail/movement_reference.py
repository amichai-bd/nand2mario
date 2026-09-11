"""Independent integer-step expectations for the frozen Springtrail rules."""
from dataclasses import dataclass, replace

UNIT=16
TILE=128
WIDTH=128
HEIGHT=256


# Stage base column, width, player x limit and camera limit; the three stages
# share one 256-column collision page. Stage0 is the unchanged original world.
STAGE_BASE=(0,96,176)
STAGE_COLUMNS=(96,80,80)
STAGE_X_MAX=(760,632,632)
STAGE_CAMERA_MAX=(608,480,480)


def solid(column,row,stage=0):
    if not 0<=column<STAGE_COLUMNS[stage] or not 0<=row<18:
        return False
    if stage==0:
        if row in (16,17):
            return not (22<=column<=25 or 46<=column<=49 or 70<=column<=73)
        return ((row==12 and (10<=column<=14 or 56<=column<=60))
                or (row==10 and 31<=column<=35) or (row==11 and 80<=column<=84))
    if stage==1:
        if row in (16,17):
            return not (18<=column<=21 or 40<=column<=43 or 62<=column<=65)
        return ((row==12 and 8<=column<=12) or (row==11 and 30<=column<=34)
                or (row==10 and 52<=column<=56) or (row==13 and 70<=column<=74))
    if row in (16,17):
        return not (14<=column<=17 or 30<=column<=33 or 46<=column<=49 or 62<=column<=65)
    return ((row==13 and 6<=column<=10) or (row==12 and (24<=column<=28 or 70<=column<=74))
            or (row==11 and 38<=column<=42) or (row==10 and 54<=column<=58))


def world_tile(column,row,stage=0):
    if solid(column,row,stage):return 11
    return 0


@dataclass(frozen=True)
class Player:
    x:int=24*UNIT
    y:int=112*UNIT
    vx:int=0
    vy:int=0
    grounded:bool=True
    previous:int=0
    camera:int=0
    fell:bool=False


def step(player,buttons):
    """One normal-frame update; no observed DUT value enters this function."""
    if player.fell:
        return replace(player,previous=buttons)
    direction=(buttons&3)
    vx=(32 if buttons&32 else 16)*(1 if direction==1 else -1 if direction==2 else 0)
    vy=-84 if buttons&16 and not player.previous&16 and player.grounded else player.vy
    vy=min(vy+4,64)
    x=max(0,min(760*UNIT,player.x+vx))
    if x!=player.x+vx:
        vx=0
    if vx:
        column=(x+WIDTH-1)//TILE if vx>0 else x//TILE
        rows=range(player.y//TILE,(player.y+HEIGHT-1)//TILE+1)
        if any(solid(column,row) for row in rows):
            x=column*TILE-WIDTH if vx>0 else (column+1)*TILE
            vx=0
    y=player.y+vy
    grounded=False
    if vy:
        row=(y+HEIGHT-1)//TILE if vy>0 else y//TILE
        columns=range(x//TILE,(x+WIDTH-1)//TILE+1)
        if any(solid(column,row) for column in columns):
            grounded=vy>0
            y=row*TILE-HEIGHT if vy>0 else (row+1)*TILE
            vy=0
    return Player(x,y,vx,vy,grounded,buttons,max(0,min(608,x//UNIT-72)),y>=144*UNIT)
