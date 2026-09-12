"""Fixed thrower/shot/hurt renderer operands; nothing is selected from DUT state."""
from motion_render_reference import Check as MotionCheck
from entities_frames import tiles, scene
from power_frames import courier
from composition_reference import raster
from hud_reference import image
from power_reference import Shot, THROWER
from entities_reference import World
from motion_reference import Player

# Large WALK2 right at world (120,12) with a live shot at (140,40), then a
# second composer stage writes large-hurt facing left at screen (60,32).
GAME = World(mode=1, power=THROWER, player=Player(x=120*16, y=12*16, camera=97, pose=2),
             shot=Shot(140*16, 40*16, 32, -32, 20))
# Six courier rather than four, plus one live shot:31 base slots.
SECONDARY = 0xc100+31*4


class Check(MotionCheck):
    def __init__(self, short=False, source_lcd=None):
        super().__init__(short,source_lcd)
        self.game = GAME
        self.base = scene(self.game)
        self.extra = courier(15, True, 60, 32)
        self.secondary_base = SECONDARY
        offset = SECONDARY-0xc100
        assert offset+len(self.extra)<=160 and self.base[offset:] == bytes(160-offset), 'POWER_RENDER_LAYOUT'
        self.shadow = self.base[:offset]+self.extra+bytes(160-offset-len(self.extra))
        self.images = [bytes(23040), image(self.game, object_pixels=raster(self.shadow, tiles()))]
