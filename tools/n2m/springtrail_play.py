"""Coherent paused acquisition and the autonomous Springtrail feedback player.

Acquisition boundary. Springtrail runs one game update per frame: the VBlank
interrupt sets `FramePending`; the main loop consumes it, samples JOYP into
`Buttons`, publishes the scene prepared by the previous update, waits for the
visible interval and then runs `UpdateGame` and the scene preparation before
halting for the next VBlank. Pausing the core freezes hardware anywhere in
that loop, so a paused read alone can see a half-written update. The reader
therefore advances a paused core with exact RUN_DOTS counts to the window
LY 145..152 and requires `FramePending == 0` there:

- `FramePending` is cleared only by `ConsumeFrame`, which the loop reaches
  only after the previous update and scene preparation completed, so every
  game record read in that window belongs to one completed update;
- the next update starts at LY 0, so no game record changes before the core
  leaves the window;
- the JOYP sample of this VBlank finished before LY 145 (ReadButtons is a few
  hundred dots after VBlank start), so `Buttons` holds this VBlank's sample and
  a mask written now is first sampled at the next VBlank and first applied by
  the update after it.

An observation taken there is labelled `logical`: the state of the last
completed update. The scene prepared from it is being published in this same
VBlank and is displayed in the next frame; the last completed source frame,
which SNAPSHOT returns at the same boundary, shows the update before it. The
three are never treated as interchangeable.

The play loop is observe, choose one complete eight-button mask, advance an
exact whole number of frames, observe again. Every advance is checked against
the ROM's own counters: the LY phase must be unchanged, the dot count must
equal the frames advanced and `GameTimer` must advance once per frame while
the game is playing. The strategy reads only observed state and read-only
world knowledge; no observation is ever filled from a prediction.
"""
import time

from . import generated_interfaces as abi
from .springtrail_state import (PLAYFIELD_X, UNIT, WRAM, StateFailure, decode, to_world, _models)

PERIOD = 70224
LINE = 456
LINES = 154
BOUNDARY_FIRST, BOUNDARY_LAST = 145, 152
MAX_STEP_FRAMES = 4
TITLE, PLAYING, RETRY, PAUSED, WON = range(5)
RIGHT, LEFT, A, B, SELECT, START = 1, 2, 16, 32, 64, 128
# Declared finite budget of one demonstration. Frames are emulated frames.
BUDGET = {'frames': 1500, 'actions': 1500, 'wall_seconds': 240, 'retries': 0,
          'no_progress_frames': 480}


class PlayFailure(RuntimeError):
    pass


def _dots(client, count):
    result = client.run_dots(count)
    if result['reason'] != abi.WIRE_RUN_DOTS_COUNT or result['executed'] != count:
        raise PlayFailure('STATE_RUN_STOPPED')
    return result['dot']


def observe(client, binding, *, attempts=6, record=None):
    """One coherent observation at the VBlank boundary plus its provenance.

    The core must already be paused. At most `attempts` bounded advances are
    made to reach the window; each is an exact RUN_DOTS count, so the
    returned dot is the endpoint's own completion dot, never a host estimate.
    """
    log = record or (lambda entry: None)
    dot = None
    requests = 0
    transferred = 0
    for _ in range(attempts):
        lcd = client.read_lcd_status()
        requests += 1
        if not lcd['lcdc'] & 0x80:
            dot = _dots(client, PERIOD)
            requests += 1
            log({'event': 'boundary', 'reason': 'lcd-off', 'dots': PERIOD})
            continue
        ly = lcd['ly']
        if not BOUNDARY_FIRST <= ly <= BOUNDARY_LAST:
            count = ((BOUNDARY_FIRST - ly) % LINES) * LINE
            dot = _dots(client, count)
            requests += 1
            log({'event': 'boundary', 'reason': 'ly', 'ly': ly, 'dots': count})
            continue
        chunks = [(offset, client.peek_range('wram', offset, count)) for offset, count in binding.ranges]
        requests += len(chunks)
        transferred += sum(len(data) for _offset, data in chunks)
        observation = decode(binding, chunks)
        if observation['frame_pending']:
            dot = _dots(client, LINE)
            requests += 1
            log({'event': 'boundary', 'reason': 'frame-pending', 'ly': ly, 'dots': LINE})
            continue
        if dot is None:
            dot = client.read_host(abi.HOST_REG_DOT_LO) | (client.read_host(abi.HOST_REG_DOT_HI) << 32)
            requests += 2
        epoch = client.read_host(abi.HOST_REG_SNAPSHOT_EPOCH)
        requests += 1
        provenance = {'dot': dot, 'epoch': epoch, 'ly': ly, 'stat_mode': lcd['mode'],
                      'boundary': 'vblank-complete', 'represents': 'logical',
                      'display_lag_frames': 1, 'requests': requests, 'bytes': transferred,
                      'decoder': observation['decoder'], 'rom_sha256': observation['rom_sha256']}
        return observation, provenance
    raise PlayFailure('STATE_BOUNDARY_UNREACHED')


def _pit_ahead(solid, pixel_x):
    """World x of the first ground gap at or after the player's leading column."""
    for column in range(pixel_x // 8, 96):
        if not solid(column, 16):
            return column * 8
    return None


class Strategy:
    """Observe, then choose one complete mask and a bounded advance.

    Rules use the observed player, enemy and mode plus read-only terrain and
    the reference motion model for one hop check. The strategy never writes
    game memory and never substitutes a prediction for an observation.
    """
    WAIT_X = 228          # stand here: the patrol never comes left of 240
    PATROL_LEFT = 240
    JUMP_LEAD = 6         # pixels before a gap; two in-flight updates walk 2 of them
    NEAR = 16

    def __init__(self):
        self.motion, self.power, _frames = _models()
        from movement_reference import solid
        self.solid = solid
        self.committed = None

    def hop_clears(self, observation):
        """Simulate the hop from the observed state; true when it lands past the enemy.

        The in-flight sample is applied first, then the same masks the rules
        will send: Right+A until the jump registers and through its ascent,
        Right alone afterwards. Read-only planning; nothing observed is replaced.
        """
        update = self.power.update
        world = update(to_world(observation), observation['buttons']['sampled'])
        for n in range(90):
            p = world.player
            world = update(world, RIGHT | (A if p.grounded or p.jump == 1 else 0))
            if world.mode != PLAYING:
                return False
            if n > 2 and world.player.grounded and world.player.jump == 0:
                return world.player.x > world.enemy_x + 8 * UNIT
        return False

    def choose(self, observation):
        mode = observation['mode']
        sampled = observation['buttons']['sampled']
        if mode == TITLE:
            return (START | RIGHT, 1, 'start') if not sampled & START else (RIGHT, 1, 'start-in-flight')
        if mode in (RETRY, WON, PAUSED):
            return (START, 1, 'restart') if not sampled & START else (0, 1, 'restart-in-flight')
        p, enemy = observation['player'], observation['enemy']
        x = p['pixel_x']
        if not p['grounded']:
            self.committed = None
            return (RIGHT | (A if p['jump'] == 1 else 0), 1, 'airborne-hold' if p['jump'] == 1 else 'airborne-release')
        if self.committed:
            # A chosen jump stays pressed until it is observed airborne; releasing
            # before the sampled edge applies would shorten it.
            return (RIGHT | A, 1, self.committed)
        pit = _pit_ahead(self.solid, x)
        enemy_ahead = enemy['alive'] and x < self.PATROL_LEFT
        distances = [pit - x if pit is not None else PLAYFIELD_X]
        if enemy_ahead:
            distances.append(self.WAIT_X - x)
        nearest = min(distances)
        if pit is not None and pit - x <= self.JUMP_LEAD and (not enemy_ahead or pit < self.WAIT_X):
            self.committed = 'jump-gap'
            return (RIGHT | A, 1, 'jump-gap')
        if enemy_ahead and x >= self.WAIT_X:
            if self.hop_clears(observation):
                self.committed = 'hop-enemy'
                return (RIGHT | A, 1, 'hop-enemy')
            return (0, 1, 'wait-enemy')
        return (RIGHT, MAX_STEP_FRAMES if nearest > self.NEAR else 1, 'walk')


def apply_mask(client, mask):
    if type(mask) is not int or not 0 <= mask <= 255:
        raise PlayFailure('STATE_MASK')
    client.write_host(abi.HOST_REG_INPUT, mask)
    if client.read_host(abi.HOST_REG_INPUT_EFFECTIVE) != mask:
        raise PlayFailure('STATE_INPUT')


def play(client, image, binding, strategy=None, *, budget=None, record=None, retain=None,
         clock=time.monotonic):
    """Run from RESET and the title to WON within the declared budget.

    Returns a result record; a failed attempt is reported, never retried
    beyond `budget['retries']`. On certain completion the input is released
    and the core left paused; after an uncertain completion no further traffic
    is sent.
    """
    limits = dict(BUDGET, **(budget or {}))
    strategy = strategy or Strategy()
    log = record or (lambda entry: None)
    keep = retain or (lambda step, observation, provenance: None)
    started = clock()
    result = {'status': 'FAIL', 'budget': limits, 'actions': [], 'frames': 0, 'attempts': 1,
              'observations': 0}
    result['identity'] = client.identify()
    result['load'] = client.load(image)
    client.select_input_source(abi.INPUT_SOURCE_UART)
    if client.read_host(abi.HOST_REG_INPUT_SOURCE) != abi.INPUT_SOURCE_UART:
        raise PlayFailure('STATE_SOURCE')
    try:
        apply_mask(client, 0)
        client.control('RESET')
        if client.read_host(abi.HOST_REG_STATE) != abi.STATE_PAUSED:
            client.control('HALT')
        observation, provenance = observe(client, binding, record=log)
        result['observations'] += 1
        keep(0, observation, provenance)
        if observation['mode'] != TITLE:
            raise PlayFailure('STATE_START_NOT_TITLE')
        result['reset_epoch'] = provenance['epoch']
        best_x, progress_frame = observation['player']['x'], 0
        while True:
            if len(result['actions']) >= limits['actions']:
                raise PlayFailure('STATE_BUDGET_ACTIONS')
            if result['frames'] >= limits['frames']:
                raise PlayFailure('STATE_BUDGET_FRAMES')
            if clock() - started > limits['wall_seconds']:
                raise PlayFailure('STATE_BUDGET_WALL')
            mask, frames, reason = strategy.choose(observation)
            if type(frames) is not int or not 1 <= frames <= MAX_STEP_FRAMES:
                raise PlayFailure('STATE_STEP')
            if result['frames'] + frames > limits['frames']:
                raise PlayFailure('STATE_BUDGET_FRAMES')
            apply_mask(client, mask)
            for _ in range(frames):
                _dots(client, PERIOD)
            before = observation, provenance
            observation, provenance = observe(client, binding, record=log)
            result['observations'] += 1
            result['frames'] += frames
            _check_advance(before, (observation, provenance), frames, mask)
            step = len(result['actions'])
            result['actions'].append({
                'step': step, 'mask': mask, 'frames': frames, 'reason': reason,
                'dot': provenance['dot'], 'timer': observation['timer'],
                'mode': observation['mode_name'], 'x': observation['player']['pixel_x'],
                'y': observation['player']['pixel_y'], 'enemy_x': observation['enemy']['pixel_x']})
            keep(step + 1, observation, provenance)
            if observation['player']['x'] > best_x:
                best_x, progress_frame = observation['player']['x'], result['frames']
            elif result['frames'] - progress_frame > limits['no_progress_frames']:
                raise PlayFailure('STATE_NO_PROGRESS')
            if observation['mode'] == WON:
                result['status'] = 'PASS'
                break
            if observation['mode'] == RETRY and not observation['buttons']['sampled'] & START:
                if result['attempts'] > limits['retries']:
                    raise PlayFailure('STATE_RETRY')
                result['attempts'] += 1
                best_x, progress_frame = 0, result['frames']
    except PlayFailure as failure:
        result['reason'] = str(failure)
    finally:
        result['final'] = {'mode': observation['mode_name'], 'timer': observation['timer'],
                           'x': observation['player']['pixel_x'], 'dot': provenance['dot']} if 'observation' in locals() else None
        if not client.uncertain:
            apply_mask(client, 0)
            result['released'] = True
        result['wall_seconds'] = round(clock() - started, 3)
    return result


def _check_advance(before, after, frames, mask):
    (observation, provenance), (observation2, provenance2) = before, after
    if provenance2['ly'] != provenance['ly']:
        raise PlayFailure('STATE_PHASE_DRIFT')
    if provenance2['dot'] - provenance['dot'] != frames * PERIOD:
        raise PlayFailure('STATE_DOT_DRIFT')
    if provenance2['epoch'] != provenance['epoch']:
        raise PlayFailure('STATE_EPOCH_CHANGED')
    delta = (observation2['timer'] - observation['timer']) & 0xFFFF
    if delta > frames:
        raise PlayFailure('STATE_TIMER_DRIFT')
    steady = observation['mode'] == PLAYING and observation2['mode'] == PLAYING
    if steady and not (observation['buttons']['sampled'] | mask) & START and delta != frames:
        raise PlayFailure('STATE_TIMER_DRIFT')
