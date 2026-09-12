"""ROM-bound Springtrail state reader: selected WRAM ranges to structured state.

The decoder is versioned and bound to exact images. A package supplies the ROM
and the linker's `symbols.json`; every address comes from those symbols, never
from a literal in this module. An unsupported image, a symbol layout that does
not belong to the image, a missing range or a byte outside the game's own
value contract is rejected. Nothing here predicts state: the caller supplies
observed bytes and gets back either a complete decoded observation or a
`StateFailure`.

The reconstructed frame reuses the independent Springtrail renderers under
`src/dv/springtrail`; it reads its dynamic state from the observation and its
terrain and artwork from the software sources.
"""
import hashlib
import json
import sys
from pathlib import Path

from . import generated_interfaces as abi
from .records import file_hash

ROOT = Path(__file__).resolve().parents[2]
DECODER_VERSION = 2
# Exact qualified images: ROM sha256 -> digest of the required symbol layout.
SUPPORTED = {
    '5d0c168c371f58f08584fefe633701684b47e9bb00500f7d5322c61ba8c410e0':
        '4b6e6b2b4770081f79160332d0106ebc8b3003c5010d9bd46917c841ffb842bf',
}
MODES = ('TITLE', 'PLAYING', 'RETRY', 'PAUSED', 'WON', 'TIMEUP', 'OVER')
HUD_WORDS = ('TITLE', 'PLAY', 'RETRY', 'PAUSED', 'WON', 'TIMEUP', 'OVER')
UNIT = 16
PLAYFIELD_X = 760 * UNIT
EFFECT_TILES = (0, 124, 128, 132, 136)
# (symbol, byte size, signed) in the order state.asm declares them.
FIELDS = (
    ('GameMode', 1, False), ('PlayerX', 2, True), ('PlayerY', 2, True),
    ('VelocityX', 2, True), ('VelocityY', 2, True), ('Grounded', 1, False),
    ('Buttons', 1, False), ('Previous', 1, False), ('Camera', 2, False),
    ('Fell', 1, False), ('GamePrevious', 1, False), ('EnemyX', 2, True),
    ('EnemyVX', 1, True), ('Score', 1, False), ('GameTimer', 2, False),
    ('Collected', 1, False), ('NewLevel', 1, False), ('FramePending', 1, False),
    ('PublishedCamera', 1, False), ('MoveCounter', 1, False), ('MoveDirection', 1, False),
    ('MoveSpeed', 1, False), ('MovePhase', 1, False), ('AnimationCounter', 1, False),
    ('MotionPose', 1, False), ('JumpState', 1, False), ('JumpIndex', 1, False),
    ('SavedJumpIndex', 1, False), ('MotionFacing', 1, False), ('PowerState', 1, False),
    ('PowerPhase', 1, False), ('PowerTimer', 1, False), ('Invincible', 1, False),
    ('ThrowTimer', 1, False), ('EnemyAlive', 1, False), ('Crouch', 1, False),
    ('ShotX', 2, True), ('ShotY', 2, True), ('ShotVX', 1, True), ('ShotVY', 1, True),
    ('ShotTTL', 1, False), ('BlockState', 4, False), ('Coins', 1, False),
    ('EffectTile', 1, False), ('EffectX', 2, True), ('EffectY', 2, True),
    ('EffectTimer', 1, False), ('BlockDirty', 1, False),
    ('Lives', 1, False), ('PendingLife', 1, False), ('TimerSub', 1, False),
    ('TimerLow', 1, False), ('TimerHigh', 1, False), ('Expiring', 1, False),
    ('StageIndex', 1, False),
)
REQUIRED = tuple(name for name, _size, _signed in FIELDS)
WRAM = abi.GB_WRAM_START
WRAM_BYTES = abi.GB_WRAM_END - abi.GB_WRAM_START + 1


class StateFailure(ValueError):
    """The observation is unsupported, incomplete or outside the game contract."""


def layout_digest(symbols):
    return hashlib.sha256(json.dumps({name: symbols[name] for name in REQUIRED},
                                     sort_keys=True).encode()).hexdigest()


def coalesce(spans, gap):
    """Merge sorted (offset, count) spans whose separation is at most `gap`."""
    merged = []
    for offset, count in sorted(spans):
        if merged and offset - (merged[-1][0] + merged[-1][1]) <= gap:
            last_offset, last_count = merged[-1]
            merged[-1] = (last_offset, max(last_count, offset + count - last_offset))
        else:
            merged.append((offset, count))
    return tuple(merged)


class Binding:
    """One qualified image, its symbol layout and the ranges the reader needs."""

    def __init__(self, rom_sha256, symbols, *, gap=48, package=None):
        if rom_sha256 not in SUPPORTED:
            raise StateFailure('STATE_ROM_UNSUPPORTED')
        missing = [name for name in REQUIRED if name not in symbols]
        if missing:
            raise StateFailure('STATE_SYMBOLS_MISSING ' + ' '.join(missing))
        if layout_digest(symbols) != SUPPORTED[rom_sha256]:
            raise StateFailure('STATE_LAYOUT_MISMATCH')
        for name, size, _signed in FIELDS:
            address = symbols[name]
            if not WRAM <= address <= address + size - 1 <= abi.GB_WRAM_END:
                raise StateFailure('STATE_SYMBOL_OUTSIDE_WRAM ' + name)
        self.rom_sha256 = rom_sha256
        self.symbols = {name: symbols[name] for name in REQUIRED}
        self.package = package
        self.ranges = coalesce(((symbols[name] - WRAM, size) for name, size, _s in FIELDS), gap)
        for _offset, count in self.ranges:
            if count > abi.WIRE_MAX_PAYLOAD:
                raise StateFailure('STATE_RANGE_TOO_LARGE')

    @property
    def bytes(self):
        return sum(count for _offset, count in self.ranges)

    def identity(self):
        return {'decoder': DECODER_VERSION, 'rom_sha256': self.rom_sha256,
                'layout_sha256': SUPPORTED[self.rom_sha256],
                'ranges': [{'offset': WRAM + offset, 'count': count} for offset, count in self.ranges],
                'requests': len(self.ranges), 'bytes': self.bytes, 'package': self.package}


def read_symbols(path):
    record = json.loads(Path(path).read_text(encoding='utf-8'))
    if record.get('schema_version') != 1 or not isinstance(record.get('symbols'), list):
        raise StateFailure('STATE_SYMBOLS_SCHEMA')
    return {entry['symbol']: entry['value'] for entry in record['symbols']
            if entry.get('unit') == 'main.asm' and isinstance(entry.get('value'), int)}


def bind_package(root, manifest):
    """Bind an immutable sw/build attempt: verified ROM plus its own symbols."""
    from .host.package import read_package
    root = Path(root)
    image, package = read_package(root, manifest)
    path = Path(manifest) if Path(manifest).is_absolute() else root / manifest
    record = json.loads(path.resolve().read_text(encoding='utf-8'))
    symbols_name = next((name for name in record['artifacts'] if name.endswith('/symbols.json')), None)
    if symbols_name is None or file_hash(Path(root) / symbols_name) != record['artifacts'][symbols_name]:
        raise StateFailure('STATE_SYMBOLS_ARTIFACT')
    binding = Binding(package['rom_sha256'], read_symbols(Path(root) / symbols_name), package=package)
    return image, binding


def _u(data, signed):
    return int.from_bytes(data, 'little', signed=signed)


def raw_fields(binding, chunks):
    """{symbol: integer} from the exact ranges the binding asked for."""
    got = {}
    for offset, data in chunks:
        if offset in got:
            # Two replies for one range cannot both be the observation.
            raise StateFailure('STATE_INCOMPLETE duplicate range')
        got[offset] = bytes(data)
    if sorted(got) != sorted(offset for offset, _count in binding.ranges):
        raise StateFailure('STATE_INCOMPLETE ranges')
    for offset, count in binding.ranges:
        if len(got[offset]) != count:
            raise StateFailure('STATE_INCOMPLETE length')
    values = {}
    for name, size, signed in FIELDS:
        start = binding.symbols[name] - WRAM
        for offset, count in binding.ranges:
            if offset <= start and start + size <= offset + count:
                data = got[offset][start - offset:start - offset + size]
                values[name] = list(data) if name == 'BlockState' else _u(data, signed)
                break
    return values


def _check(condition, what):
    if not condition:
        raise StateFailure('STATE_MALFORMED ' + what)


def decode(binding, chunks):
    """Structured observation, or StateFailure. No field is ever guessed."""
    v = raw_fields(binding, chunks)
    _check(0 <= v['GameMode'] < len(MODES), 'GameMode')
    _check(v['StageIndex'] < 3, 'StageIndex')
    stage = v['StageIndex']
    for name in ('Lives', 'TimerLow'):
        _check(v[name] >> 4 <= 9 and v[name] & 15 <= 9, name)
    _check(1 <= v['TimerSub'] <= 40, 'TimerSub')
    _check(v['TimerHigh'] <= 9, 'TimerHigh')
    _check(v['Expiring'] in (0, 1, 2, 3, 255), 'Expiring')
    _check(0 <= v['PlayerX'] <= (760, 632, 632)[stage] * UNIT, 'PlayerX')
    _check(0 <= v['PlayerY'] <= 160 * UNIT, 'PlayerY')
    _check(-2 * UNIT <= v['VelocityX'] <= 2 * UNIT, 'VelocityX')
    _check(-4 * UNIT <= v['VelocityY'] <= 4 * UNIT, 'VelocityY')
    for flag in ('Grounded', 'Fell', 'NewLevel', 'FramePending', 'EnemyAlive', 'Crouch'):
        _check(v[flag] in (0, 1), flag)
    # A cheap secondary check, not the protection against a partly written
    # record: the camera is clamped, so wherever the clamp is active (the first
    # 72 pixels and the right end) a torn record passes it unseen. The paused
    # acquisition boundary is what actually prevents tears; see
    # wiki/tools/host-play/SPEC.md#springtrail-state-reconstruction.
    _check(v['Camera'] == max(0, min((608, 480, 480)[stage], v['PlayerX'] // UNIT - 72)), 'Camera')
    _check((240, 240, 272)[stage] * UNIT <= v['EnemyX'] <= (296, 296, 328)[stage] * UNIT, 'EnemyX')
    _check(v['EnemyVX'] in (8, -8), 'EnemyVX')
    _check(v['Collected'] <= 15 and v['Score'] == bin(v['Collected']).count('1'), 'Score')
    # MoveCounter and AnimationCounter are free bytes; the contract bounds the rest.
    _check(v['MoveDirection'] <= 3, 'MoveDirection')
    _check(v['MoveSpeed'] in (0, 2, 4), 'MoveSpeed')
    _check(v['MovePhase'] <= 1, 'MovePhase')
    _check(v['MotionPose'] <= 5, 'MotionPose')
    _check(v['JumpState'] <= 3, 'JumpState')
    _check(v['JumpIndex'] <= 26 and v['SavedJumpIndex'] <= 25, 'JumpIndex')
    _check(v['MotionFacing'] in (0, 32), 'MotionFacing')
    _check(v['PowerState'] <= 2 and v['PowerPhase'] <= 3, 'PowerState')
    _check(v['PowerTimer'] <= 96 and v['Invincible'] <= 248 and v['ThrowTimer'] <= 8, 'PowerTimer')
    _check(v['ShotTTL'] <= 64, 'ShotTTL')
    _check(all(state <= 2 for state in v['BlockState']), 'BlockState')
    _check(v['EffectTile'] in EFFECT_TILES and v['EffectTimer'] <= 16, 'Effect')
    _check(v['BlockDirty'] <= 96, 'BlockDirty')
    mode = v['GameMode']
    return {
        'decoder': DECODER_VERSION, 'rom_sha256': binding.rom_sha256,
        'mode': mode, 'mode_name': MODES[mode],
        'player': {'x': v['PlayerX'], 'y': v['PlayerY'], 'vx': v['VelocityX'], 'vy': v['VelocityY'],
                   'pixel_x': v['PlayerX'] // UNIT, 'pixel_y': v['PlayerY'] // UNIT,
                   'grounded': bool(v['Grounded']), 'fell': bool(v['Fell']),
                   'pose': v['MotionPose'], 'facing': 'left' if v['MotionFacing'] else 'right',
                   'jump': v['JumpState'], 'jump_index': v['JumpIndex'],
                   'saved_index': v['SavedJumpIndex'], 'counter': v['MoveCounter'],
                   'direction': v['MoveDirection'], 'speed': v['MoveSpeed'],
                   'phase': v['MovePhase'], 'animation': v['AnimationCounter']},
        'camera': v['Camera'], 'published_camera': v['PublishedCamera'],
        'enemy': {'x': v['EnemyX'], 'pixel_x': v['EnemyX'] // UNIT, 'vx': v['EnemyVX'],
                  'alive': bool(v['EnemyAlive'])},
        'items': {'collected': v['Collected'], 'score': v['Score']},
        'timer': v['GameTimer'], 'new_level': v['NewLevel'],
        'progress': {'stage': stage, 'lives': v['Lives'], 'pending': v['PendingLife'],
                     'timer_sub': v['TimerSub'], 'timer_low': v['TimerLow'],
                     'timer_high': v['TimerHigh'], 'expiring': v['Expiring']},
        'power': {'state': v['PowerState'], 'phase': v['PowerPhase'], 'timer': v['PowerTimer'],
                  'invincible': v['Invincible'], 'throw': v['ThrowTimer'], 'crouch': bool(v['Crouch'])},
        'shot': {'x': v['ShotX'], 'y': v['ShotY'], 'vx': v['ShotVX'], 'vy': v['ShotVY'], 'ttl': v['ShotTTL']},
        'blocks': {'states': v['BlockState'], 'coins': v['Coins'],
                   'effect': {'tile': v['EffectTile'], 'x': v['EffectX'], 'y': v['EffectY'],
                              'timer': v['EffectTimer']},
                   'dirty': v['BlockDirty']},
        'hud': {'word': HUD_WORDS[mode], 'score': v['Score']},
        'buttons': {'sampled': v['Buttons'], 'applied': v['Previous'], 'game_previous': v['GamePrevious']},
        'frame_pending': v['FramePending'],
    }


_LOADED = {}


def _import(*names):
    """Import Springtrail models without leaving their generic names behind.

    The models import each other by bare name, so the directory has to be on
    the path while they load, and they land in `sys.modules` under names like
    `reference`, which `src/dv/v05` also owns. Both the path entry and the
    names the import added are restored afterwards, and the module objects are
    cached here instead; they keep working because their own globals hold
    direct references. This follows the same structural guard as
    `tools/n2m/tests/stackdrop_support.py`.
    """
    missing = [name for name in names if name not in _LOADED]
    if missing:
        folder = str(ROOT / 'src/dv/springtrail')
        before = dict(sys.modules)
        path = list(sys.path)
        sys.path.insert(0, folder)
        try:
            for name in missing:
                _LOADED[name] = __import__(name)
        finally:
            for name in set(sys.modules) - set(before):
                del sys.modules[name]
            sys.modules.update(before)
            sys.path[:] = path
    return tuple(_LOADED[name] for name in names)


def _models():
    """The motion and contact rules; no artwork and no renderer."""
    return _import('motion_reference', 'progress_reference')


def to_world(observation):
    """The reference World for one observation; rendering and planning only."""
    motion, power = _models()
    p, o = observation['player'], observation
    player = motion.Player(
        x=p['x'], y=p['y'], vx=p['vx'], vy=p['vy'], grounded=p['grounded'],
        previous=o['buttons']['applied'], camera=o['camera'], fell=p['fell'],
        counter=p['counter'], direction=p['direction'], speed=p['speed'], phase=p['phase'],
        animation=p['animation'], pose=p['pose'], jump=p['jump'], index=p['jump_index'],
        saved=p['saved_index'], facing=32 if p['facing'] == 'left' else 0)
    shot_type, = _import('power_reference')
    shot = shot_type.Shot(o['shot']['x'], o['shot']['y'], o['shot']['vx'], o['shot']['vy'], o['shot']['ttl'])
    effect = o['blocks']['effect']
    return power.World(
        player=player, mode=o['mode'], enemy_x=o['enemy']['x'], enemy_vx=o['enemy']['vx'],
        collected=o['items']['collected'], score=o['items']['score'], timer=o['timer'],
        previous=o['buttons']['game_previous'], power=o['power']['state'],
        phase=o['power']['phase'], phase_timer=o['power']['timer'],
        invincible=o['power']['invincible'], throw=o['power']['throw'],
        alive=o['enemy']['alive'], crouch=o['power']['crouch'], shot=shot,
        blocks=tuple(o['blocks']['states']), coins=o['blocks']['coins'],
        effect_tile=effect['tile'], effect_x=effect['x'], effect_y=effect['y'],
        effect_timer=effect['timer'], block_dirty=o['blocks']['dirty'],
        **o['progress'])


def render(observation):
    """160 by 144 shades of the logical state, through the block-layer renderer."""
    world = to_world(observation)
    frames, = _import('blocks_frames')
    return frames.image(world)


def reconstruction(observation, provenance):
    """A labelled reconstructed image record; pixels stay beside it, not in it."""
    pixels = render(observation)
    return {'reconstructed': True, 'label': 'RECONSTRUCTED from observed game state; not a PPU frame',
            'represents': 'logical', 'width': 160, 'height': 144,
            'pixels_sha256': hashlib.sha256(pixels).hexdigest(),
            'decoder': DECODER_VERSION, 'rom_sha256': observation['rom_sha256'],
            'provenance': dict(provenance)}, pixels
