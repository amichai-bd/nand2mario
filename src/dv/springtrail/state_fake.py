"""A byte-level fake endpoint that serves Springtrail state from the models.

The fake owns an independent timeline and an independent WRAM encoding. Game
state comes from `progress_reference.update`, and the WRAM bytes are written
through the existing independent fixture encoder `blocks_cases.state_bytes`
over `blocks_cases.ADDRESSES`. The reader under test finds the same bytes
through the linker's symbol table, so the two agree only if both are right.

The timeline mirrors `src/sw/springtrail/main.asm`. For frame g starting at
`LCD + g * PERIOD`:

| offset | event |
|---|---|
| 0 | `UpdateGame` runs with the mask sampled in VBlank g-1, then prepares the scene. Game records are torn until it finishes. |
| 65664 | VBlank g begins: the ISR sets `FramePending`; source frame g is complete. |
| 65664 + 300 | `ConsumeFrame` clears `FramePending`, `ReadButtons` samples INPUT into `Buttons`, and `PublishScene` publishes the scene prepared from the update at offset 0. |

So an observation taken after the consume and before the next offset 0 sees
exactly one completed update, which is the boundary the reader requires.

No serial port, no simulator and no board is involved.
"""
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from n2m import generated_interfaces as abi  # noqa: E402
from n2m.interface_codec import decode_packet, encode_packet, pack_pixels, pack_record, unpack_record  # noqa: E402
import blocks_cases  # noqa: E402
import blocks_frames  # noqa: E402
import progress_cases  # noqa: E402
from progress_reference import PLAYING, World, update  # noqa: E402

PERIOD = 70224
LINE = 456
VBLANK = 144 * LINE
CONSUME = 300
# The frozen startup anchor of the current image. The reader never depends on
# it: it locates the boundary from LY, so a moved anchor only costs an advance.
LCD = 177308
UPDATE_DOTS = 20000  # how long game records stay torn after offset 0
BUILD_ID = '0f1e2d3c4b5a69788796a5b4c3d2e1f0'
WRAM_BYTES = abi.GB_WRAM_END - abi.GB_WRAM_START + 1
FRAME_PENDING, PUBLISHED_CAMERA = 0xC050, 0xC051


def reachable(script):
    """A start world the model itself produced, so every field is reachable.

    `script` is a sequence of `(mask, repeat)` pairs applied through
    `progress_reference.update` from the title state. Building fixtures this way
    keeps cross-field invariants such as the camera true by construction; a
    hand-written record would not be a state the ROM can ever hold.
    """
    world = World()
    for mask, repeat in script:
        for _ in range(repeat):
            world = update(world, mask)
    return world


def wram_image(world, buttons, new_level, frame_pending, published_camera, torn=None):
    """WRAM bytes for one state, written only through the fixture encoder.

    `torn` is the world an in-progress update started from: position, velocity
    and motion already hold the new state while the camera and everything after
    it still hold the old one. That is the order the update writes them in, so
    it is what a read inside the update window would actually return.
    """
    memory = bytearray(WRAM_BYTES)
    def place(source, addresses):
        encoded = blocks_cases.state_bytes(source, buttons, new_level)
        for address, value in zip(blocks_cases.ADDRESSES, encoded):
            if address in addresses:
                memory[address - abi.GB_WRAM_START] = value
    progress_source = torn if torn is not None else world
    for address, value in zip(progress_cases.ADDRESSES,
                              progress_cases.state_bytes(progress_source, buttons, new_level)):
        if address >= 0xc090:
            memory[address - abi.GB_WRAM_START] = value
    # Camera at C01B is computed last, after the move; the tear splits there.
    player_record = set(range(0xC010, 0xC01B)) | set(range(0xC060, 0xC06A))
    if torn is None:
        place(world, set(blocks_cases.ADDRESSES))
    else:
        place(torn, set(blocks_cases.ADDRESSES) - player_record)
        place(world, player_record)
    memory[FRAME_PENDING - abi.GB_WRAM_START] = frame_pending
    memory[PUBLISHED_CAMERA - abi.GB_WRAM_START] = published_camera & 0xFF
    return bytes(memory)


class Game:
    """The fake's emulated Springtrail endpoint: timeline, WRAM and frames."""

    def __init__(self, *, defect=None, start=None, delay=0):
        self.defect = defect
        self.delay = delay        # consumes that sample neutral, as a late start
        self.mask = 0             # the endpoint INPUT register the ROM samples
        self.start = start if start is not None else World()
        self.reset()

    def reset(self):
        self.dot = 0
        self.world = self.start
        self.previous = self.world
        self.sampled = 0          # WRAM Buttons: the mask this VBlank sampled
        self.new_level = 0
        self.frame_pending = 0
        self.published_camera = 0
        self.published = self.world   # scene published at the last VBlank
        self.displayed = self.world   # the last completed source frame
        self.frame = -1               # completed source frame sequence
        self.frame_dot = 0
        self.updating_from = None     # set while an update is in progress
        self.updates = 0
        self.consumes = 0
        self.pending_frame = None

    # ------------------------------------------------------------- timeline
    def _events(self, start, end):
        """Every scheduled event strictly after `start` and at or before `end`."""
        if end < LCD:
            return []
        events = []
        first = max(0, (max(start, LCD) - LCD) // PERIOD)
        last = (end - LCD) // PERIOD
        for g in range(first, last + 1):
            base = LCD + g * PERIOD
            for offset, name in ((0, 'update'), (UPDATE_DOTS, 'settled'),
                                 (VBLANK, 'vblank'), (VBLANK + CONSUME, 'consume')):
                when = base + offset
                if start < when <= end and when >= LCD:
                    events.append((when, name, g))
        return sorted(events)

    def advance(self, count):
        end = self.dot + count
        for when, name, g in self._events(self.dot, end):
            self.dot = when
            self._fire(name, g)
        self.dot = end
        return self.dot

    def _fire(self, name, g):
        if name == 'update':
            if g == 0:
                return  # the first update follows the first sample
            self.updating_from = self.world
            after = update(self.world, self.sampled)
            if after.crouch:
                self.sampled &= ~3
            if self.world.mode != PLAYING and after.mode == PLAYING:
                self.new_level = 1
            elif self.new_level:
                self.new_level = 0
            self.previous, self.world = self.world, after
            self.updates += 1
        elif name == 'settled':
            self.updating_from = None
        elif name == 'vblank':
            self.displayed = self.published
            self.frame, self.frame_dot = g, self.dot
            self.frame_pending = 1
        elif name == 'consume':
            self.frame_pending = 0
            self.consumes += 1
            self.sampled = self.mask
            if self.defect == 'ignore-input' or self.consumes <= self.delay:
                self.sampled = 0
            self.published = self.world
            self.published_camera = self.world.player.camera

    # --------------------------------------------------------------- views
    @property
    def ly(self):
        return 0 if self.dot < LCD else ((self.dot - LCD) % PERIOD) // LINE

    @property
    def lcdc(self):
        return 0x91 if self.dot >= LCD else 0

    def wram(self):
        pending = self.frame_pending
        if self.defect == 'stuck-pending':
            pending = 1
        elif self.defect == 'pending-once' and self.pending_frame != self.frame:
            # Read once per frame before the consume: a settling advance, not a
            # stuck flag. The reader must retry and account for the dots.
            self.pending_frame = self.frame
            pending = 1
        return wram_image(self.world, self.sampled, self.new_level, pending,
                          self.published_camera, torn=self.updating_from)

    def pixels(self):
        return blocks_frames.image(self.displayed)


class Endpoint:
    """Wire-level transport fake: `write(packet)` then `read(count)`."""

    def __init__(self, defect=None, start=None, *, image=b'', delay=0):
        self.defect = defect
        self.game = Game(defect=defect, start=start, delay=delay)
        self.rom = bytearray(abi.PROFILE_ROM_BYTES)
        self.expected_crc = None
        self.present = set()
        self.state = abi.STATE_PAUSED
        self.valid = 0
        self.profile = 0
        self.mask = 0
        self.source = abi.INPUT_SOURCE_UART
        self.epoch = 2
        self.snapshot = None
        self.pending = bytearray()
        self.requests = []
        self.peeks = []
        self.writes = []
        self.closed = False
        self.timeout = 2
        if image:
            self.rom[:] = image

    # ------------------------------------------------------------ commands
    def _read_host(self, address):
        game = self.game
        values = {
            abi.HOST_REG_ABI: abi.WIRE_ABI, abi.HOST_REG_STATE: self.state,
            abi.HOST_REG_IMAGE_VALID: self.valid, abi.HOST_REG_PROFILE: self.profile,
            abi.HOST_REG_INPUT: self.mask, abi.HOST_REG_INPUT_SOURCE: self.source,
            abi.HOST_REG_INPUT_PHYSICAL: 0,
            abi.HOST_REG_INPUT_EFFECTIVE: self.mask if self.source == abi.INPUT_SOURCE_UART else 0,
            abi.HOST_REG_DOT_LO: game.dot & 0xFFFFFFFF, abi.HOST_REG_DOT_HI: game.dot >> 32,
            abi.HOST_REG_SNAPSHOT_EPOCH: self.epoch,
            abi.HOST_REG_SNAPSHOT_VALID: int(self.snapshot is not None),
            abi.HOST_REG_IO_LCDC: game.lcdc, abi.HOST_REG_IO_LY: game.ly,
            abi.HOST_REG_IO_STAT: 0x40 | (1 if game.ly >= 144 else 3),
        }
        values.update({getattr(abi, f'HOST_REG_BUILD_ID_{i}'):
                       int.from_bytes(bytes.fromhex(BUILD_ID)[i * 4:i * 4 + 4], 'little') for i in range(4)})
        values[abi.HOST_REG_IO_LCD_STATUS] = ((values[abi.HOST_REG_IO_LCDC] << 16)
                                              | (values[abi.HOST_REG_IO_STAT] << 8) | game.ly)
        for name in ('SCY', 'SCX', 'LYC', 'BGP', 'OBP0', 'OBP1', 'WY', 'WX',
                     'DIV', 'TIMA', 'TMA', 'TAC', 'IF', 'IE'):
            values.setdefault(getattr(abi, 'HOST_REG_IO_' + name), 0)
        if self.defect == 'zero-build':
            values.update({getattr(abi, f'HOST_REG_BUILD_ID_{i}'): 0 for i in range(4)})
        return values[address]

    def write(self, packet):
        header, payload = decode_packet(packet)
        name = next(item['name'] for item in abi.COMMANDS
                    if getattr(abi, 'COMMAND_' + item['name']) == header['command'])
        self.requests.append(name)
        status, response = abi.STATUS_OK, b''
        game = self.game
        if name == 'PING':
            response = pack_record('word', {'value': abi.WIRE_ABI})
        elif name == 'READ_HOST':
            address = unpack_record('read_host', payload)['address']
            response = pack_record('word', {'value': self._read_host(address)})
        elif name == 'WRITE_HOST':
            request = unpack_record('write_host', payload)
            self.writes.append((request['address'], request['value']))
            if request['address'] == abi.HOST_REG_INPUT:
                self.mask = request['value']
                if self.defect != 'input-stuck':
                    game.mask = self.mask
            else:
                self.source = request['value']
            response = pack_record('dot', {'dot': game.dot})
        elif name == 'LOAD_BEGIN':
            request = unpack_record('load_begin', payload)
            self.profile, self.expected_crc = request['profile'], request['crc32']
            self.state, self.valid = abi.STATE_LOADING, 0
            self.present.clear()
        elif name == 'LOAD_WRITE':
            offset = int.from_bytes(payload[:4], 'little')
            self.rom[offset:offset + len(payload) - 4] = payload[4:]
            self.present.update(range(offset, offset + len(payload) - 4))
        elif name == 'LOAD_END':
            if len(self.present) != len(self.rom) or zlib.crc32(self.rom) != self.expected_crc:
                status = abi.STATUS_BAD_IMAGE
            else:
                self.valid, self.state = 1, abi.STATE_PAUSED
        elif name == 'READ_ROM':
            request = unpack_record('read_range', payload)
            response = bytes(self.rom[request['offset']:request['offset'] + request['count']])
        elif name == 'RESET':
            self.epoch += 1
            game.reset()
            game.mask = self.mask
            self.snapshot = None
            self.state = abi.STATE_PAUSED
        elif name == 'RUN_DOTS':
            count = unpack_record('word', payload)['value']
            if self.state != abi.STATE_PAUSED or not self.valid:
                status = abi.STATUS_BAD_STATE
            else:
                executed = count // 2 if self.defect == 'short-run' else count
                game.advance(executed)
                response = pack_record('run_dots', {
                    'dot': game.dot, 'executed': executed,
                    'reason': abi.WIRE_RUN_DOTS_COUNT if executed == count else abi.WIRE_RUN_DOTS_STOPPED})
        elif name == 'HALT':
            self.state = abi.STATE_PAUSED
            response = pack_record('dot', {'dot': game.dot})
        elif name == 'RUN':
            self.state = abi.STATE_RUNNING
        elif name == 'INPUT':
            self.mask = unpack_record('input', payload)['buttons']
            game.mask = self.mask
            response = pack_record('dot', {'dot': game.dot})
        elif name == 'PEEK':
            request = unpack_record('peek_range', payload)
            if self.state != abi.STATE_PAUSED:
                status = abi.STATUS_BAD_STATE
            elif request['store'] != abi.PEEK_WRAM:
                status = abi.STATUS_BAD_VALUE
            else:
                self.peeks.append((request['offset'], request['count']))
                response = game.wram()[request['offset']:request['offset'] + request['count']]
                if self.defect == 'short-peek':
                    response = response[:-1]
        elif name == 'SNAPSHOT':
            if game.frame < 0:
                status = abi.STATUS_BAD_STATE
            else:
                self.snapshot = pack_pixels(game.pixels())
                response = pack_record('snapshot', {'epoch': self.epoch, 'seq': game.frame,
                                                    'dot': game.frame_dot, 'size': abi.FRAME_BYTES})
        elif name == 'READ_FRAME':
            request = unpack_record('read_range', payload)
            response = self.snapshot[request['offset']:request['offset'] + request['count']]
        if self.defect == 'timeout':
            return len(packet)
        frame = encode_packet(header['seq'], header['command'], response,
                              kind=abi.WIRE_RESPONSE, status=status)
        self.pending.extend(frame)
        return len(packet)

    def read(self, count):
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result

    def close(self):
        self.closed = True
