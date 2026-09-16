"""Source-derived visible-preparation bound for the current Springtrail image.

The main loop must finish UpdateGame, PrepareScene, PrepareHUD, PrepareProgress
and PrepareMap inside the 65664 visible dots before the same next publication.
This module derives the scene and shot components from the actual routines by
running them on the independent SM83 timing model (`startup_anchor.Model`)
over exhaustive branch-relevant operand domains, then composes the reachable
profiles the entity plan records. Nothing here reads DUT output.

Composition is a sum of maxima. PrepareScene is a fixed sequence of composers
whose costs add; each composer's own overhead is enumerated over its branch
operands, every emitted piece is charged the exhaustive EmitPiece maximum, and
the zero tail is charged for the largest population. The shot's Update cost is
the exhaustive StepShot maximum plus the spawn path and its timer, added to
the plan's stage-0 update profiles; later stages have no blocks, so no thrower.
"""
import bisect
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[2] / 'tools')]
from startup_anchor import Model  # noqa: E402
from state_support import build  # noqa: E402
from state_fake import wram_image  # noqa: E402
from entities_reference import World, initialize  # noqa: E402
from power_reference import Shot  # noqa: E402
from motion_reference import Player  # noqa: E402
from progress_reference import PLAYING  # noqa: E402
from n2m import generated_interfaces as abi  # noqa: E402

VISIBLE = 65664
PUBLICATION = 4480
EMIT_LABELS = {'EmitPiece', 'PieceXPositive', 'PieceXReady', 'PieceYPositive', 'PieceYReady',
               'PieceStore', 'PieceYZero', 'PieceOwnerHidden'}
TAIL_LABELS = {'ClearSceneByte', 'ClearSceneEntry', 'ClearSceneNext'}
# Population classes: FULL is a large courier with a live shot and a live release
# effect on stage 0; SMALL is the small courier with no shot or effect, which is
# every later stage (no block reaches their pages, so no thrower) and every
# stage-0 frame before the first block is reachable.
FULL, SMALL = 'full', 'small'
PIECES = {FULL: 35, SMALL: 28}
# Reachable update profiles of the entity plan: (name, update, map, other,
# population, shot). The scene column is derived here; update/map/other are the
# plan's source bounds. `shot` charges the live-shot update delta; idle modes run
# no world update, and a reset clears the shot before any restoration frame.
PROFILES = (
    ('stage0 air ascent without ceiling', 24292, 2412, 1796, FULL, True),
    ('stage0 air descent', 25260, 2412, 1796, FULL, True),
    ('stage0 interactive underside hit', 24096, 4108, 1796, FULL, True),
    ('stage0 noninteractive terrain ceiling', 26744, 2412, 1796, FULL, True),
    ('stage0 terrain supported', 27036, 2412, 1796, FULL, True),
    ('stage0 groundloss topRow8', 25932, 2412, 1796, FULL, True),
    ('stage0 groundloss topRow9', 26208, 2412, 1796, FULL, True),
    ('stage0 groundloss topRow10', 24596, 2412, 1796, FULL, True),
    ('stage0 groundloss topRow14', 26916, 2412, 1796, FULL, True),
    ('stage0 moving supported', 26536, 2412, 1796, FULL, True),
    ('stage0 falling supported', 26536, 2412, 1796, FULL, True),
    ('stage0 moving supportloss', 27376, 2412, 1796, FULL, True),
    ('stage0 falling successfulcarry supportloss', 26928, 2412, 1796, FULL, True),
    ('stage0 falling failedcarry', 27580, 2412, 1796, FULL, True),
    ('later-stage ordinary noncarrier', 29956, 2412, 1796, SMALL, False),
    ('later-stage ordinary carrier upper', 27952, 2412, 1796, SMALL, False),
    ('early stage restoration/title transition', 29956, 4108, 1860, SMALL, False),
    ('idle/reset/next-stage modes', 5400, 4108, 1860, FULL, False),
)


class Source:
    """The current image on the timing model, with labelled cost attribution."""

    def __init__(self):
        self.rom, self.labels = build()
        # Shared addresses keep one name for attribution; poke uses the full map.
        self.symbols = {}
        for name in sorted(self.labels, reverse=True):
            self.symbols[self.labels[name]] = name
        self.addresses = sorted(self.symbols)
        cpu = Model(self.rom)
        while cpu.lcd is None:
            cpu.mcycles += cpu.step()
        self.booted = bytes(cpu.memory)
        self.cpu = cpu

    def label(self, pc):
        index = bisect.bisect_right(self.addresses, pc) - 1
        return self.symbols[self.addresses[index]]

    def reset(self):
        self.cpu.memory[:] = self.booted
        return self.cpu

    def call(self, entry, profile=None, bound=100000):
        """Dots from entry through RET, attributed by label when asked."""
        cpu = self.cpu
        cpu.pc, cpu.sp = self.labels[entry], 0xdffc
        cpu.memory[0xdffc:0xdffe] = bytes((255, 127))
        cycles = 0
        while cpu.pc != 0x7fff:
            pc = cpu.pc
            step = cpu.step()
            cycles += step
            if profile is not None:
                profile[self.label(pc)] += step * 4
            assert cycles < bound, 'VISIBLE_BOUND_ROUTINE'
        return cycles * 4

    def poke(self, name, value, width=1):
        address = self.labels[name]
        self.cpu.memory[address:address + width] = (value & (256 ** width - 1)).to_bytes(width, 'little')

    def load(self, world, buttons=0):
        image = wram_image(world, buttons, 0, 0, world.player.camera)
        self.cpu.memory[abi.GB_WRAM_START:abi.GB_WRAM_START + len(image)] = image


def emit_piece_max(source):
    """Exhaustive EmitPiece maximum over every clipping and hidden branch."""
    best = 0
    for hidden in (0, 1):
        for base_x in range(-320, 880):
            for piece_x in (0, 8, 16):
                cpu = source.reset()
                source.poke('SceneHidden', hidden)
                source.poke('SceneBaseX', base_x, 2)
                source.poke('SceneBaseY', 40, 2)
                cpu.b, cpu.c, cpu.d, cpu.e = piece_x, 8, 0xc1, 0x40
                best = max(best, source.call('EmitPiece'))
    for base_y in range(-320, 480):
        for piece_y in (0, 8, 16):
            cpu = source.reset()
            source.poke('SceneHidden', 0)
            source.poke('SceneBaseX', 40, 2)
            source.poke('SceneBaseY', base_y, 2)
            cpu.b, cpu.c, cpu.d, cpu.e = 8, piece_y, 0xc1, 0x40
            best = max(best, source.call('EmitPiece'))
    return best


def _scene_world(**changes):
    """Every entity on screen so each composer runs its full path."""
    player = Player(x=80 * 16, y=112 * 16, camera=0, grounded=True)
    world = initialize(World(mode=PLAYING, player=player, enemy_x=40 * 16))
    world = replace(world, curl=replace(world.curl, x=120 * 16, y=64 * 16),
                    moving=replace(world.moving, x=32 * 16, y=80 * 16),
                    falling=replace(world.falling, x=112 * 16, y=104 * 16))
    return replace(world, **changes)


def _rest(source, world):
    """(rest, emit, tail, pieces): PrepareScene dots outside EmitPiece and the tail."""
    source.reset()
    source.load(world)
    profile = Counter()
    total = source.call('PrepareScene', profile)
    emit = sum(profile[label] for label in EMIT_LABELS)
    tail = sum(profile[label] for label in TAIL_LABELS)
    pieces = _pieces(source)
    return total - emit - tail, emit, tail, pieces


def _pieces(source):
    shadow = source.cpu.memory[0xc100:0xc1a0]
    count = 0
    for index in range(0, 160, 4):
        if any(shadow[index:index + 4]):
            count = index // 4 + 1
    return count


def composer_variants(world):
    """Branch operands of each composer, one composer at a time."""
    large = replace(world, power=1)
    return {
        'courier': [world, large, replace(world, player=replace(world.player, facing=32)),
                    replace(large, player=replace(large.player, facing=32)),
                    replace(world, player=replace(world.player, fell=True)),
                    replace(large, player=replace(large.player, fell=True)),
                    replace(large, crouch=True), replace(large, throw=4)],
        'patrol': [world, replace(world, patrol_frame=8), replace(world, enemy_vx=-8),
                   replace(world, alive=False, stomp=12), replace(world, alive=False, stomp=4),
                   replace(world, alive=False, stomp=0)],
        'items': [world, replace(world, collected=15)],
        'shot': [world, replace(world, power=2, shot=Shot(90 * 16, 100 * 16, 32, 32, 20))],
        'effect': [world, replace(world, effect_tile=124, effect_x=64 * 16, effect_y=48 * 16, effect_timer=8)],
        'curl': [world, replace(world, curl=replace(world.curl, state=1, timer=16)),
                 replace(world, curl=replace(world.curl, state=2))],
        'moving': [world, replace(world, moving=replace(world.moving, state=0))],
        'falling': [world, replace(world, falling=replace(world.falling, state=1, timer=12)),
                    replace(world, falling=replace(world.falling, state=1, timer=4)),
                    replace(world, falling=replace(world.falling, state=2)),
                    replace(world, falling=replace(world.falling, state=3))],
    }


def tail_cost(source, pieces):
    """Zero-tail dots for a population, from the actual routine."""
    cpu = source.reset()
    cpu.a, cpu.d, cpu.e = 0, 0xc1, 4 * pieces
    return source.call('ClearSceneByte') if pieces < 40 else 0


def scene_cap(source, emit_max, population):
    """Sum of composer maxima plus the population at the piece maximum."""
    base = _scene_world()
    rest_base, _, _, _ = _rest(source, base)
    deltas = {}
    for name, variants in composer_variants(base).items():
        if population == SMALL and name in ('shot', 'effect'):
            continue
        if population == SMALL and name == 'courier':
            variants = [variant for variant in variants if variant.power == 0]
        deltas[name] = max(_rest(source, variant)[0] - rest_base for variant in variants)
    pieces = PIECES[population]
    total = rest_base + sum(deltas.values()) + pieces * emit_max + tail_cost(source, pieces)
    return dict(cap=total, rest=rest_base, deltas=deltas, pieces=pieces,
                emit_max=emit_max, tail=tail_cost(source, pieces))


def select_pose_extra(source):
    """Pose selection varies with power, phase, timers and mode; charge its spread."""
    costs = []
    for power in (0, 1, 2):
        for phase, timer in ((0, 0), (1, 5), (1, 1), (2, 5), (2, 1), (3, 5), (3, 1)):
            for throw in (0, 4):
                for crouch in (0, 1):
                    for pose in (0, 4, 5):
                        for mode in (1, 2):
                            source.reset()
                            for name, value in (('GameMode', mode), ('PowerState', power), ('PowerPhase', phase),
                                                ('PowerTimer', timer), ('ThrowTimer', throw), ('Crouch', crouch),
                                                ('MotionPose', pose)):
                                source.poke(name, value)
                            costs.append(source.call('SelectCourier'))
    return max(costs) - min(costs)


def step_shot_max(source, offsets=(1, 97)):
    """StepShot over every stage-0 cell, tile-crossing offsets, velocities and block states."""
    best = 0
    for state in ((0, 0, 0, 0), (1, 2, 1, 1)):
        for column in range(0, 95):
            for row in range(0, 18):
                for kx in offsets:
                    for ky in offsets:
                        for vx, vy in ((32, 32), (32, 0xe0), (0xe0, 32), (0xe0, 0xe0)):
                            source.reset()
                            source.poke('EnemyAlive', 1)
                            source.poke('EnemyX', 256 * 16, 2)
                            source.poke('StageIndex', 0)
                            address = source.labels['BlockState']
                            source.cpu.memory[address:address + 4] = bytes(state)
                            source.poke('ShotX', column * 128 + kx, 2)
                            source.poke('ShotY', row * 128 + ky, 2)
                            source.poke('ShotVX', vx)
                            source.poke('ShotVY', vy)
                            source.poke('ShotTTL', 64)
                            best = max(best, source.call('StepShot'))
    return best


def step_shot_offsets(source, cells=((86, 10), (87, 10), (88, 11), (63, 10), (64, 11), (37, 10), (20, 16), (0, 0))):
    """Every sub-tile offset class at representative cells proves the two-offset sweep covers the branches."""
    best = 0
    for column, row in cells:
        for kx in (0, 1, 31, 32, 33, 95, 96, 97, 127):
            for ky in (0, 1, 31, 32, 33, 95, 96, 97, 127):
                for vx, vy in ((32, 32), (32, 0xe0), (0xe0, 32), (0xe0, 0xe0)):
                    source.reset()
                    source.poke('EnemyAlive', 1)
                    source.poke('EnemyX', 256 * 16, 2)
                    source.poke('ShotX', column * 128 + kx, 2)
                    source.poke('ShotY', row * 128 + ky, 2)
                    source.poke('ShotVX', vx)
                    source.poke('ShotVY', vy)
                    source.poke('ShotTTL', 64)
                    best = max(best, source.call('StepShot'))
    return best


def shot_update_delta(source):
    """Update dots a live or spawning shot adds over the no-shot profiles."""
    source.reset()
    source.poke('ShotTTL', 0)
    idle = source.call('StepShot')
    inputs = []
    for power in (0, 1, 2):
        for grounded in (0, 1):
            for jump in (0, 1):
                for buttons in (0, 8, 32, 40):
                    for pressed in (0, 32):
                        for ttl in (0, 5):
                            source.reset()
                            for name, value in (('PowerState', power), ('Grounded', grounded), ('JumpState', jump),
                                                ('Buttons', buttons), ('Pressed', pressed), ('ShotTTL', ttl)):
                                source.poke(name, value)
                            source.poke('PlayerX', 500 * 16, 2)
                            source.poke('PlayerY', 112 * 16, 2)
                            inputs.append(source.call('PowerInput'))
    timers = {}
    for throw in (0, 8):
        costs = []
        for phase, timer in ((0, 0), (1, 5), (1, 1), (2, 1), (3, 1)):
            for invincible in (0, 5):
                source.reset()
                for name, value in (('PowerPhase', phase), ('PowerTimer', timer), ('Invincible', invincible),
                                    ('ThrowTimer', throw)):
                    source.poke(name, value)
                costs.append(source.call('PowerTimers'))
        timers[throw] = max(costs)
    step = max(step_shot_max(source), step_shot_offsets(source))
    return dict(step_shot_max=step, step_shot_idle=idle, power_input_max=max(inputs),
                power_input_min=min(inputs), throw_timer=timers[8] - timers[0],
                delta=step - idle + max(inputs) - min(inputs) + max(0, timers[8] - timers[0]))


def derive(source=None):
    source = source or Source()
    emit = emit_piece_max(source)
    extra = select_pose_extra(source)
    scenes = {population: scene_cap(source, emit, population) for population in (FULL, SMALL)}
    for scene in scenes.values():
        scene['cap'] += extra
    shot = shot_update_delta(source)
    rows = []
    for name, update, map_dots, other, population, live_shot in PROFILES:
        scene = scenes[population]['cap']
        delta = shot['delta'] if live_shot else 0
        total = update + delta + scene + map_dots + other
        rows.append(dict(profile=name, population=population, update=update, shot=delta, scene=scene,
                         map=map_dots, other=other, total=total, margin=VISIBLE - total))
    return dict(emit_piece_max=emit, select_pose_extra=extra, scenes=scenes, shot=shot, rows=rows,
                visible=VISIBLE, worst=min(row['margin'] for row in rows))


def main():
    result = derive()
    print(f"EmitPiece max {result['emit_piece_max']}; pose selection spread {result['select_pose_extra']}")
    for population, scene in result['scenes'].items():
        print(f"{population} scene cap {scene['cap']} = rest {scene['rest']} + deltas {scene['deltas']} "
              f"+ {scene['pieces']} x {scene['emit_max']} + tail {scene['tail']}")
    print('shot', result['shot'])
    print(f"{'profile':46s}{'update':>8s}{'shot':>6s}{'scene':>7s}{'map':>6s}{'other':>6s}{'total':>7s}{'margin':>7s}")
    for row in result['rows']:
        print(f"{row['profile']:46s}{row['update']:8d}{row['shot']:6d}{row['scene']:7d}{row['map']:6d}"
              f"{row['other']:6d}{row['total']:7d}{row['margin']:7d}")
    print('worst margin', result['worst'])
    return 0 if result['worst'] >= 0 else 1


if __name__ == '__main__':
    sys.exit(main())
