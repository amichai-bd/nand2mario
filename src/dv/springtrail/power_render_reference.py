"""Fixed thrower/shot/hurt renderer operands; nothing is selected from DUT state."""
from motion_render_reference import Check as MotionCheck
from motion_frames import tiles
from power_frames import scene, courier
from composition_reference import raster
from hud_reference import image
from power_reference import World, Shot, THROWER
from motion_reference import Player

# Large WALK2 right at world (120,12) with a live shot at (140,40), then a
# second composer stage writes large-hurt facing left at screen (60,32).
GAME = World(mode=1, power=THROWER, player=Player(x=120*16, y=12*16, camera=97, pose=2),
             shot=Shot(140*16, 40*16, 32, -32, 20))
SECONDARY = 0xc150


class Check(MotionCheck):
    def __init__(self, short=False):
        super().__init__(short)
        self.game = GAME
        self.base = scene(self.game)
        self.extra = courier(15, True, 60, 32)
        self.secondary_base = SECONDARY
        offset = SECONDARY-0xc100
        assert self.base[offset:] == bytes(160-offset), 'POWER_RENDER_LAYOUT'
        self.shadow = self.base[:offset]+self.extra+bytes(160-offset-len(self.extra))
        self.images = [bytes(23040), image(self.game, object_pixels=raster(self.shadow, tiles()))]
