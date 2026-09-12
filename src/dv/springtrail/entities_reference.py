"""Original bounded entity rules; expectations never read assembled code or DUT state."""
from dataclasses import dataclass, fields, replace

import motion_reference as motion
import power_reference as power
import progress_reference as progress
from movement_reference import solid, STAGE_X_MAX, STAGE_CAMERA_MAX

U = 16
MOVING_LO = (176, 144, 112)
CURL_X = (328, 352, 328)
FALL_X = (368, 320, 368)


@dataclass(frozen=True)
class Entity:
    x: int = 0
    y: int = 0
    state: int = 0
    timer: int = 0
    vx: int = 0


@dataclass(frozen=True)
class World(progress.World):
    curl: Entity = Entity(328*U,120*U)
    moving: Entity = Entity(176*U,112*U,1,0,U)
    falling: Entity = Entity(368*U,112*U)
    patrol_frame: int = 0
    stomp: int = 0
    rider: int = 0


def initialize(world):
    values = {f.name:getattr(world,f.name) for f in fields(progress.World)}
    stage = world.stage
    return World(**values, curl=Entity(CURL_X[stage]*U,120*U),
                 moving=Entity(MOVING_LO[stage]*U,112*U,1,0,U),
                 falling=Entity(FALL_X[stage]*U,112*U))


def spawn(world, slot):
    """Fixed slots have one owner; only absent slots can be reinitialized explicitly."""
    if slot not in (0,1,2,3):
        return world, False
    fresh = initialize(world)
    if slot == 0:
        if world.alive or world.stomp:
            return world, False
        return replace(world, alive=True, enemy_x=power.STAGE_ENEMY_START[world.stage],
                       enemy_vx=8, patrol_frame=0, stomp=0), True
    name = ('curl','moving','falling')[slot-1]
    entity = getattr(world,name)
    absent = (entity.state == 2 if slot == 1 else entity.state == 3)
    if not absent:
        return world, False
    return replace(world, **{name:getattr(fresh,name)}), True


def _overlap_x(player, entity):
    return player.x < entity.x+24*U and entity.x < player.x+8*U


def _live(entity, falling=False):
    return entity.state != 3 if falling else entity.state == 1


def _platforms(world):
    moving, falling = world.moving, world.falling
    if moving.state == 1:
        lo, hi = MOVING_LO[world.stage]*U, (MOVING_LO[world.stage]+32)*U
        x = moving.x+moving.vx
        moving = replace(moving, x=max(lo,min(hi,x)),
                         vx=-U if x>=hi else U if x<=lo else moving.vx)
    if falling.state == 1:
        timer = falling.timer-1
        falling = replace(falling,timer=timer,state=1 if timer else 2)
    if falling.state == 2:
        y = falling.y+2*U
        falling = replace(falling,y=y,state=3 if y>=144*U else 2)
    return moving, falling


def _carry(player, dx, dy, stage, blocked):
    x = max(0,min(STAGE_X_MAX[stage]*U,player.x+dx))
    y = player.y+dy
    # Carry is bounded to two pixels; test the swept box, preserving ordinary
    # half-open terrain/block contacts and never treating an entity as terrain.
    if x != player.x+dx:
        return player, False
    for row in range(min(player.y,y)//128,(max(player.y,y)+255)//128+1):
        for col in range(min(player.x,x)//128,(max(player.x,x)+127)//128+1):
            if solid(col,row,stage) or (blocked and blocked(col,row,dy<0)):
                return player, False
    return replace(player,x=x,y=y), True


def _curl(entity, player):
    if entity.state == 2:
        return entity
    if entity.state == 1:
        return replace(entity,timer=entity.timer-1) if entity.timer>1 else replace(entity,state=0,timer=32)
    if entity.timer:
        return replace(entity,timer=entity.timer-1)
    return replace(entity,state=1,timer=32) if abs(player.x-entity.x)<=32*U else entity


def world_step(world, buttons, timers=False):
    old_player = world.player
    old_platforms = (world.moving,world.falling)
    new_platforms = _platforms(world)
    world = replace(world,moving=new_platforms[0],falling=new_platforms[1],
                    patrol_frame=(world.patrol_frame+1)&15,stomp=max(0,world.stomp-1),rider=0)
    rider = 0
    jump_edge = bool(buttons&16 and not old_player.previous&16)
    for i,entity in enumerate(old_platforms):
        if (_live(entity,i==1) and old_player.grounded and old_player.jump==0
                and old_player.y+256==entity.y and _overlap_x(old_player,entity)):
            rider = i+1
            break
    landed = [0]
    detached = set()

    def step_player(player, masked, blocked, report, stage):
        if rider and not jump_edge:
            before,after = old_platforms[rider-1],new_platforms[rider-1]
            if _live(after,rider==2):
                player,ok = _carry(player,after.x-before.x,after.y-before.y,stage,blocked)
                if ok:
                    landed[0] = rider
                else:
                    detached.add(rider-1)

        def support(p):
            return any(i not in detached and _live(e,i==1) and p.y+256==e.y and _overlap_x(p,e)
                       for i,e in enumerate(new_platforms))

        p = motion.step(player,masked,blocked,report,stage,support=support)
        landed[0] = 0
        if p.vy >= 0 and p.jump != 1:
            for i,(before,after) in enumerate(zip(old_platforms,new_platforms)):
                if (i not in detached and _live(after,i==1) and old_player.y+256<=before.y
                        and p.y+256>=after.y and _overlap_x(p,after)):
                    p = replace(p,y=after.y-256,vy=0,grounded=True,jump=0,index=0,saved=0,fell=False)
                    landed[0] = i+1
                    break
        return replace(p,camera=max(0,min(STAGE_CAMERA_MAX[stage],p.x//U-72)))

    def contacts(w):
        w = replace(w,curl=_curl(w.curl,w.player),rider=landed[0])
        if landed[0]==2 and w.falling.state==0:
            w = replace(w,falling=replace(w.falling,state=1,timer=16))
        was_stomp = (w.alive and not w.invincible and power.overlap(w,w.enemy_x,power.ENEMY_Y)
                     and (w.player.y+256)//U-120<=4 and not w.player.fell)
        w = power.enemy_contact(w)
        if was_stomp and not w.alive:
            w = replace(w,stomp=16)
        if w.mode == power.RETRY or w.curl.state != 1 or not power.overlap(w,w.curl.x,w.curl.y):
            return w
        if w.invincible:
            return replace(w,curl=replace(w.curl,state=2,timer=0))
        if w.phase in (power.HURT,power.SAFE):
            return w
        if w.power != power.SMALL:
            return replace(w,power=power.SMALL,phase=power.HURT,phase_timer=32,throw=0)
        return replace(w,mode=power.RETRY)

    return power.world_update(world,buttons,timers=timers,step_player=step_player,contacts=contacts)


def update(world, buttons):
    result = progress.update(world,buttons,world_step=world_step)
    reset = (not isinstance(result,World) or
             (world.mode in (progress.RETRY,progress.TIMEUP,progress.WON,progress.OVER)
              and result.mode==progress.PLAYING) or
             (world.mode==progress.PAUSED and buttons&64 and not world.previous&64))
    return initialize(result) if reset else result
