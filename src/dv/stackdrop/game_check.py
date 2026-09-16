"""Literal startup/input schedule and complete image oracle for the game."""
from reference import Game
from screen import image, TITLE_SCROLL
from cases import buffer

LCD = 185948  # 1648 atlas bytes at 52 dots each, plus the fixed prefix.
# SCY, SCX: the title page before LCD enable, then the play page once, in the
# VBlank that copies the first playing image.
SCROLL = ((0xff42, TITLE_SCROLL[1]), (0xff43, TITLE_SCROLL[0]), (0xff42, 0), (0xff43, 0))
INPUT_WINDOW = (LCD+30000, LCD+32000)
END = LCD+2*70224+65480
TITLE = Game()
PLAY = Game(status=1)
FRAMES = (bytes(23040), image(TITLE), image(PLAY))
ADDRESSES = [0x9866+y*32+x for y in range(12) for x in range(8)]
ADDRESSES += [0x988f+y*32+x for y in range(4) for x in range(4)]
ADDRESSES += list(range(0x996f, 0x9973))+[0x99ef, 0x99f0]


class Check:
    def __init__(self):
        self.pixels = 0
        self.last_pixel = 0
        self.lcd = []
        self.inputs = []
        self.copies = [[], [], []]
        self.prepared = []
        self.scroll = []

    def pixel(self, value):
        frame, index = divmod(self.pixels, 23040)
        assert frame < 3, 'STACKDROP_EXTRA_FRAME'
        y, x = divmod(index, 160)
        dot = value >> 53
        expected = (2 << 21) | (x << 13) | (y << 5) | (FRAMES[frame][index] << 3) | (int(index == 0) << 2) | int(frame != 0)
        assert value & ((1 << 53)-1) == expected, f'STACKDROP_PIXEL frame={frame} index={index} expected={expected:x} actual={value & ((1 << 53)-1):x}'
        start = LCD+frame*70224+y*456
        assert start <= dot < start+456 and dot > self.last_pixel, 'STACKDROP_PIXEL_TIME'
        self.last_pixel = dot
        self.pixels += 1

    def write(self, value):
        dot, address, data = value >> 24, (value >> 8) & 65535, value & 255
        if address == 0xff40:
            expected = ((52, 0), (LCD, 145))
            assert len(self.lcd) < 2 and (dot, data) == expected[len(self.lcd)], f'STACKDROP_LCD dot={dot} data={data}'
            self.lcd.append((dot, data))
        if address in (0xff42, 0xff43):
            assert len(self.scroll) < 4 and (address, data) == SCROLL[len(self.scroll)], f'STACKDROP_SCROLL dot={dot} address={address:x} data={data}'
            assert (dot <= LCD) == (len(self.scroll) < 2), f'STACKDROP_SCROLL_TIME dot={dot}'
            self.scroll.append(dot)
        if dot <= LCD:
            return
        if 0x9800 <= address < 0x9c00:
            frame, offset = divmod(dot-LCD, 70224)
            assert frame < 3 and 65664 <= offset < 70224, f'STACKDROP_VBLANK_WRITE dot={dot} offset={offset}'
            self.copies[frame].append((dot, address, data))
        if address == 0xc275:
            self.prepared.append(dot)

    def input(self, value):
        epoch, dot, buttons = value >> 72, (value >> 8) & ((1 << 64)-1), value & 255
        assert not self.inputs and epoch == 2 and INPUT_WINDOW[0] <= dot <= INPUT_WINDOW[1] and buttons == 128, 'STACKDROP_INPUT'
        self.inputs.append(dot)

    def finish(self, pause):
        assert self.lcd == [(52, 0), (LCD, 145)], f'STACKDROP_LCD {self.lcd}'
        assert self.pixels == 69120 and len(self.inputs) == 1, 'STACKDROP_MISSING_FRAME'
        assert END <= pause <= END+2000, 'STACKDROP_FINAL_BOUND'
        for frame, game in enumerate((TITLE, PLAY)):
            assert [(a, v) for _, a, v in self.copies[frame]] == list(zip(ADDRESSES, buffer(game))), 'STACKDROP_FRAME_COPY'
            assert len(self.prepared) > frame, 'STACKDROP_MISSING_PREPARATION'
            first_vblank = LCD+65664+frame*70224
            assert first_vblank < self.prepared[frame] < first_vblank+70224, 'STACKDROP_PREPARATION_BUDGET'
        # The final HALT may interrupt the third VBlank copy after the last
        # checked frame; it must still be an exact prefix of the stable image.
        tail = [(a, v) for _, a, v in self.copies[2]]
        assert tail == list(zip(ADDRESSES, buffer(PLAY)))[:len(tail)], 'STACKDROP_TAIL_COPY'
        # The one scroll change follows the second copy inside the same VBlank.
        second = LCD+70224+65664
        assert len(self.scroll) == 4 and self.copies[1][-1][0] < self.scroll[2] < self.scroll[3] < second+4560, f'STACKDROP_SCROLL_WINDOW {self.scroll}'
        return dict(pixels=self.pixels, pause_dot=pause, input_dots=self.inputs,
                    last_pixel_dot=self.last_pixel, preparation_dots=self.prepared,
                    complete_copy_last_dots=[rows[-1][0] for rows in self.copies[:2]],
                    scroll_dots=self.scroll, scroll_vblank_offsets=[d-second for d in self.scroll[2:]])
