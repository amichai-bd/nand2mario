"""Independent entity scene from approved maps and ordinary logical state."""
from entities_art import pieces, tiles as entity_tiles
from power_frames import scene as power_scene, courier, selected_pose, player_hidden
from blocks_frames import effect, background
from motion_frames import tiles as prior_tiles
from hud_reference import image as hud_image


def tiles():
    return prior_tiles() + [[list(tile[y*8:y*8+8]) for y in range(8)] for tile in entity_tiles()]


def pose(name,x,y,hidden=False,left=False):
    data=bytearray()
    for px,py,tile,fx,fy in pieces(name,left):
        sx,sy=x+px,y+py
        visible=not hidden and -7<=sx<160 and -7<=sy<144
        data.extend(((sy+16)&255 if visible else 0,(sx+8)&255,tile,32*fx+64*fy))
    return bytes(data)


def scene(world):
    p=world.player
    tail=effect(world)
    base=power_scene(world,tail)
    n=len(courier(selected_pose(world),bool(p.facing),p.x//16-p.camera-4,p.y//16,player_hidden(world)))
    used=n+8+40+(4 if world.shot.ttl else 0)+len(tail)
    patrol=('BEETLE WALK2' if world.patrol_frame&8 else 'BEETLE WALK1') if world.alive else (
        'BEETLE STOMP1' if world.stomp>8 else 'BEETLE STOMP2')
    data=bytearray(base[:n])+pose(patrol,world.enemy_x//16-p.camera-4,112,
                                 not world.alive and not world.stomp,world.enemy_vx<0)
    data+=base[n+8:used]
    data+=pose('CURL ACTIVE' if world.curl.state==1 else 'CURL DORMANT',
               world.curl.x//16-p.camera-4,world.curl.y//16-8,world.curl.state==2)
    data+=pose('PLATFORM SOLID',world.moving.x//16-p.camera,world.moving.y//16,world.moving.state!=1)
    name='PLATFORM SOLID' if world.falling.state==0 else (
        'PLATFORM CRACK1' if world.falling.timer>8 else 'PLATFORM CRACK2')
    data+=pose(name,world.falling.x//16-p.camera,world.falling.y//16,world.falling.state==3)
    assert len(data)<=160
    return bytes(data)+bytes(160-len(data))


def image(world):
    return hud_image(world,object_pixels=background(world,scene(world),tiles()))
