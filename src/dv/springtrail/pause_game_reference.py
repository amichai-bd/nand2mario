"""Pause and Select-restart frames on the current image; no DUT value selects a state.

The script is fixed before execution. Mask n is sampled in VBlank n, its
update is computed in visible frame n+1, published in VBlank n+1 and displayed
in frame n+2. Frames 0..5 are checked pixel by pixel: blank, TITLE, the first
world frame, a neutral frame, the PAUSED frame and the Select-restart frame.
"""
from motion_frames import scene, image
from motion_game_reference import ADDRESSES, PERIOD, state_bytes, update
from motion_reference import Player
from hud_reference import hud_tiles, column, progress_tiles, PROGRESS_ROW
from interactions_reference import Game, TITLE, PLAYING

# Sampled JOYP masks for VBlank 0..4; VBlank 5 samples the held final mask.
SCRIPT = (129, 0, 128, 64, 64)
FRAMES = len(SCRIPT) + 1
PUBLICATIONS = FRAMES + 1  # LCD-off initialization plus VBlank 0..5.
INPUT_WINDOW = (60000, 62000)
PREPARE_CEILING = 49280
TITLE_ROWS = tuple(range(0x98a4, 0x98af)) + tuple(range(0x98e4, 0x98ef))


def states():
    result = [Game(player=Player())]
    for mask in SCRIPT:
        result.append(update(result[-1], mask))
    return result


def samples():
    """Every VBlank sample, including the held mask in the final VBlank."""
    return SCRIPT + (SCRIPT[-1],)


def new_level(previous, current):
    """A published level start: leaving TITLE, or a fresh restart of PLAYING."""
    if current.mode == TITLE:
        return False
    if previous.mode == TITLE:
        return True
    return previous.mode != PLAYING and current.mode == PLAYING and current.timer == 0


def restoration(games):
    """Prepared column pairs per update and the map reselect per publication.

    The counter starts complete; a level start restarts it at column 0 and
    each later publication restores the next pair until all 32 are written.
    """
    counter = 32
    pairs, reselect = [None], [False]
    for index in range(1, len(games)):
        start = new_level(games[index-1], games[index])
        if start:
            pair = (0, 1)
        elif counter < 32:
            pair = (counter, counter+1)
        else:
            pair = None
        pairs.append(pair)
        if start:
            counter = 0
        if pair is not None:
            counter += 2
        reselect.append(start)
    return pairs, reselect


def hud_writes(game):
    result = []
    for base in (0x9800, 0x9c00):
        result += list(zip([base+i for i in range(1, 7)]+[base+18], hud_tiles(game)))
    return result


def progress_writes(game, static):
    """The six row1 value cells, to the map the display shows after this VBlank."""
    base = 0x9820 if static else 0x9c20
    return [(base+col, tile) for (col, source, _), tile in zip(PROGRESS_ROW, progress_tiles(game))
            if source != 'icon']


def column_writes(pair):
    if pair is None:
        return []
    return [(0x9c40+(c & 31)+y*32, v) for c in pair for y, v in enumerate(column(c))]


def publication_writes(games, index, pairs, reselect):
    """Exact ordered display writes of VBlank `index`, from the source contract."""
    writes = [(0xff43, 0), (0xff42, 0), (0xff40, 0x91)]
    if reselect[index]:
        if games[index-1].mode == TITLE:
            writes += [(a, 0) for a in TITLE_ROWS]
        writes.append((0xff40, 0x91))
    writes += column_writes(pairs[index])
    writes += hud_writes(games[index])
    # The static map stays selected through the title and until the pair that
    # completes the ring; the progression row goes to the selected map only.
    pair = pairs[index]
    static = games[index].mode == TITLE or (pair is not None and pair[0]+2 < 32)
    writes += progress_writes(games[index], static)
    writes.append((0xff46, 0xc1))
    return writes


class Check:
    def __init__(self, short=False):
        self.short = short
        self.states = states()
        self.pairs, self.reselect = restoration(self.states)
        self.images = [bytes(23040)]+[image(g) for g in self.states[:FRAMES-1]]
        self.lcd = None; self.memory = {}; self.partial = []; self.ready = []
        self.pixels = 0; self.frames = [bytearray() for _ in range(FRAMES)]
        self.triggers = []; self.dma = []
        self.ended = False; self.records = 0; self.last_record = 0; self.input_dots = []
        self.tiles = []; self.lines = 0; self.inputs = []
        self.tokens = []; self.irq = []; self.sources = []; self.split = []; self.vb_writes = []
        self.hud = []; self.hud_partial = []; self.cache = []; self.bus_trigger = None
        self.bus_count = 0; self.samples = []; self.restores = []

    @property
    def count(self):
        return 1 if self.short else PUBLICATIONS

    def next_input(self, dot):
        """Index of the next scripted mask due at `dot`, or None."""
        n = len(self.input_dots)
        if self.short or self.lcd is None or n >= len(SCRIPT)-1:
            return None
        if dot >= self.lcd+n*PERIOD+INPUT_WINDOW[0]:
            return n
        return None

    def input_window(self, n):
        return (self.lcd+n*PERIOD+INPUT_WINDOW[0], self.lcd+n*PERIOD+INPUT_WINDOW[1])

    def pixel(self, value):
        frame, index = divmod(self.pixels, 23040)
        assert self.lcd is not None and frame < FRAMES, 'PAUSE_EXTRA_PIXEL'
        y, x = divmod(index, 160)
        want = (2 << 21)|(x << 13)|(y << 5)|(self.images[frame][index] << 3)|(int(index == 0) << 2)|int(frame != 0)
        assert value & ((1 << 53)-1) == want, f'PAUSE_PIXEL frame={frame} index={index}'
        dot = value >> 53
        assert self.lcd+frame*PERIOD+y*456 <= dot < self.lcd+frame*PERIOD+(y+1)*456, 'PAUSE_ROW'
        self.frames[frame].append((value >> 3) & 3); self.pixels += 1

    def line(self, text):
        assert not self.ended, 'PAUSE_AFTER_END'
        kind, raw = text.strip().split(' ')
        if kind == 'END':
            assert int(raw) == self.lines and not self.partial, 'PAUSE_END'
            self.ended = True; return
        self.lines += 1
        value = int(raw, 16)
        if kind == 'P': self.pixel(value); return
        if kind == 'I':
            epoch, dot, buttons = value >> 72, (value >> 8) & ((1 << 64)-1), value & 255
            n = len(self.inputs)
            assert not self.short and n < len(SCRIPT)-1 and epoch == 2 and buttons == SCRIPT[n], 'PAUSE_INPUT'
            low, high = self.input_window(n)
            assert self.lcd is not None and low <= dot <= high, 'PAUSE_INPUT_WINDOW'
            self.inputs.append(dot); return
        if kind == 'R':
            from test_integration import decode_record
            row = decode_record(value)
            assert row['seq'] == self.records and row['epoch'] == 2 and row['dot'] > self.last_record, 'PAUSE_RETIRE'
            assert not row['halt_bug'], 'PAUSE_HALT_BUG'
            if row['kind'] == 1:
                assert row['pc_after'] in (0x40, 0x48), 'PAUSE_IRQ_VECTOR'
                self.irq.append((row['dot'], row['pc_after']))
            if self.triggers and self.triggers[-1]+8 <= row['dot'] <= self.triggers[-1]+644:
                assert row['kind'] == 0 and 0xff80 <= row['pc_before'] <= 0xfffe and row['ime'] == 0, 'PAUSE_DMA_IRQ'
            self.records += 1; self.last_record = row['dot']; return
        assert kind == 'W', 'PAUSE_TRACE_KIND'
        dot, address, data = value >> 24, (value >> 8) & 65535, value & 255
        self.memory[address] = data
        if 0x8000 <= address < 0x8620:
            assert self.lcd is None, 'PAUSE_LATE_TILES'
            self.tiles.append((address, data))
        if address == 0xff40:
            if data == 0:
                assert self.lcd is None, 'PAUSE_LCD_OFF'
            elif self.lcd is None:
                assert data == 0x91 and 100000 < dot < 200000, 'PAUSE_STARTUP_BOUND'
                self.lcd = dot
            else:
                assert data in (0x91, 0x93), 'PAUSE_OBJECT_MODE'
        if 0xc100 <= address < 0xc1a0:
            index = len(self.ready)
            assert index < FRAMES and address == 0xc100+len(self.partial), 'PAUSE_SHADOW_ORDER'
            self.partial.append(data)
            if len(self.partial) == 160:
                assert bytes(self.partial) == scene(self.states[index]), 'PAUSE_SHADOW'
                buttons = 0 if index == 0 else SCRIPT[index-1]
                assert bytes(self.memory[a] for a in ADDRESSES) == state_bytes(self.states[index], buttons), 'PAUSE_STATE'
                if index == 0: assert self.lcd is None, 'PAUSE_INITIAL_READY'
                else: assert self.lcd+index*PERIOD <= dot < self.lcd+index*PERIOD+PREPARE_CEILING, 'PAUSE_VISIBLE_READY'
                self.ready.append(dot); self.partial = []
        if address == 0xff46:
            n = len(self.triggers)
            assert n < PUBLICATIONS and data == 0xc1, 'PAUSE_DMA_TRIGGER'
            if n == 0: assert len(self.ready) == 1 and self.lcd is None, 'PAUSE_INIT_DMA'
            else:
                assert len(self.ready) == n, 'PAUSE_PUBLISH_READY'
                assert self.lcd+(n-1)*PERIOD+65664 <= dot < self.lcd+n*PERIOD-644, 'PAUSE_VBLANK_DMA'
                assert dot+644 <= self.lcd+(n-1)*PERIOD+65664+4480, 'PAUSE_DMA_COMPLETION_BOUND'
            self.triggers.append(dot)
        if address == 0xff0f: assert self.lcd is None, 'PAUSE_PENDING_IRQ_CLEAR'
        if address == 0xc019 and self.lcd is not None:
            phase = (dot-self.lcd) % PERIOD
            if 65664 <= phase < PERIOD:
                n = len(self.samples)
                assert n < FRAMES and data == samples()[n], 'PAUSE_JOYP_SAMPLE'
                self.samples.append(dot)
            else:
                # Only a restart rewrites the sampled mask in visible time: the
                # player reset clears it, then the restart restores the sample.
                index = (dot-self.lcd)//PERIOD
                assert 1 <= index < FRAMES and self.reselect[index] and self.states[index-1].mode != TITLE, 'PAUSE_RESTART_SAMPLE'
                assert self.samples and data in (0, SCRIPT[index-1]), 'PAUSE_RESTART_SAMPLE_VALUE'
                self.restores.append((index, data))
        if address == 0xc050 and data == 1:
            assert self.lcd is not None, 'PAUSE_TOKEN_STARTUP'
            n = len(self.tokens)
            assert self.lcd+n*PERIOD+65662 <= dot <= self.lcd+n*PERIOD+65852, 'PAUSE_TOKEN_TIME'
            self.tokens.append(dot)
        if 0xc220 <= address <= 0xc226:
            index = len(self.hud)
            assert index < FRAMES and address == 0xc220+len(self.hud_partial), 'PAUSE_HUD_CACHE_ORDER'
            self.hud_partial.append(data)
            if len(self.hud_partial) == 7:
                assert bytes(self.hud_partial) == hud_tiles(self.states[index]), 'PAUSE_HUD_CACHE'
                self.hud.append(dot); self.hud_partial = []
        if 0xc200 <= address < 0xc220:
            block, offset = divmod(len(self.cache), 32)
            assert block+1 < FRAMES and self.pairs[block+1] is not None and address == 0xc200+offset, 'PAUSE_COLUMN_CACHE_ORDER'
            self.cache.append(data)
            assert data == (column(self.pairs[block+1][0])+column(self.pairs[block+1][1]))[offset], 'PAUSE_COLUMN_CACHE'
            assert self.lcd+(block+1)*PERIOD <= dot < self.lcd+(block+1)*PERIOD+PREPARE_CEILING, 'PAUSE_COLUMN_CACHE_READY'
        if self.lcd is not None and dot > self.lcd:
            phase = (dot-self.lcd) % PERIOD
            if address in (0xff40, 0xff43) and phase < 65664:
                frame = (dot-self.lcd)//PERIOD
                assert 15*456+280 <= phase <= 15*456+384, 'PAUSE_SPLIT_WINDOW'
                expected = (0xff43, 0) if len(self.split) % 2 == 0 else (0xff40, 0x93)
                assert (address, data) == expected, 'PAUSE_SPLIT_ORDER'
                self.split.append((frame, dot, address, data))
            elif 0x8000 <= address < 0xa000 or 0xfe00 <= address < 0xfea0 or address in (0xff40, 0xff42, 0xff43, 0xff46):
                assert 65664 <= phase < PERIOD, 'PAUSE_DISPLAY_WINDOW'
                assert phase < 65664+4480, 'PAUSE_PUBLICATION_BOUND'
                self.vb_writes.append((dot, address, data))

    def bus(self, raw):
        dot, address, write, data = raw >> 25, (raw >> 9) & 65535, (raw >> 8) & 1, raw & 255
        if write and address == 0xff46: self.bus_trigger = dot
        if self.bus_trigger is not None and self.bus_trigger+8 <= dot <= self.bus_trigger+644:
            assert 0xff80 <= address <= 0xfffe, 'PAUSE_DMA_BUS'
            self.bus_count += 1

    def finish(self, pause, tile_bytes):
        assert self.ended and not self.partial and not self.hud_partial, 'PAUSE_INCOMPLETE'
        assert self.tiles == list(enumerate(tile_bytes, 0x8000)), 'PAUSE_TILES'
        assert self.bus_count > 0 and self.records > 100, 'PAUSE_MISSING_PROGRESS'
        assert len(self.triggers) == self.count and len(self.dma) == 160*self.count, 'PAUSE_DMA_COUNT'
        for i, value in enumerate(self.dma):
            publication, offset = divmod(i, 160)
            want = scene(self.states[max(0, publication-1)])[offset]
            assert (value >> 18, (value >> 8) & 255, value & 255) == (self.triggers[publication]+8+4*offset, offset, want), 'PAUSE_DMA_BYTE'
        if self.short:
            assert 160 <= self.pixels < 640 and len(self.ready) == 1 and not self.input_dots, 'PAUSE_SHORT_END'
            return self.summary(pause)
        assert self.pixels == FRAMES*23040 and len(self.ready) == FRAMES and len(self.hud) == FRAMES, 'PAUSE_FRAME_COUNT'
        assert len(self.cache) == 32*sum(p is not None for p in self.pairs), 'PAUSE_COLUMN_CACHE_COUNT'
        assert len(self.tokens) == FRAMES and len(self.samples) == FRAMES, 'PAUSE_UPDATE_COUNT'
        restarts = [i for i in range(1, FRAMES) if self.reselect[i] and self.states[i-1].mode != TITLE]
        assert self.restores == [(i, v) for i in restarts for v in (0, SCRIPT[i-1])], 'PAUSE_RESTART_COUNT'
        assert [vector for _, vector in self.irq] == [0x48, 0x40]*FRAMES, 'PAUSE_IRQ_ORDER'
        assert [row[0] for row in self.split] == [f for f in range(FRAMES) for _ in (0, 1)], 'PAUSE_SPLIT_COUNT'
        expected_sources = [s for f in range(FRAMES) for s in ((self.lcd+f*PERIOD+6838, 2), (self.lcd+f*PERIOD+65662, 1))]
        assert self.sources == expected_sources, 'PAUSE_IRQ_SOURCES'
        for (dot, vector), (request, source) in zip(self.irq, self.sources):
            assert 20 <= dot-request <= 52, 'PAUSE_IRQ_LATENCY'
        for publication in range(FRAMES):
            start = self.lcd+publication*PERIOD+65664
            writes = [(address, data) for dot, address, data in self.vb_writes if start <= dot < start+PERIOD-65664]
            expected = publication_writes(self.states, publication, self.pairs, self.reselect)
            assert writes == expected, f'PAUSE_PUBLICATION vblank={publication}'
        assert len(self.input_dots) == len(self.inputs) == len(SCRIPT)-1, 'PAUSE_INPUT_COUNT'
        for n, (applied, traced) in enumerate(zip(self.input_dots, self.inputs)):
            low, high = self.input_window(n)
            assert applied == traced and low <= applied <= high, 'PAUSE_APPLIED_INPUT'
        assert self.triggers[-1]+644 < pause < self.lcd+FRAMES*PERIOD, 'PAUSE_FINAL_WINDOW'
        return self.summary(pause)

    def summary(self, pause):
        return dict(pixels=self.pixels, records=self.records, lcd=self.lcd, ready=self.ready,
                    dma_bytes=len(self.dma), input_dots=self.input_dots, pause=pause, irq=self.irq,
                    split=self.split, tokens=self.tokens, hud=self.hud, samples=self.samples,
                    restores=self.restores, bus_count=self.bus_count,
                    cache_bytes=len(self.cache))
