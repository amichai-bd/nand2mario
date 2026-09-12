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
from .host.client import UncertainCompletion
from .springtrail_state import StateFailure, UNIT, decode, to_world, _models

PERIOD = 70224
LINE = 456
LINES = 154
BOUNDARY_FIRST, BOUNDARY_LAST = 145, 152
MAX_STEP_FRAMES = 4
TITLE, PLAYING, RETRY, PAUSED, WON, TIMEUP, OVER = range(7)
# The complete eight-button mask the endpoint takes, active high.
RIGHT, LEFT, UP, DOWN, A, B, SELECT, START = 1, 2, 4, 8, 16, 32, 64, 128
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


def observe(client, binding, *, attempts=8, record=None, clock=time.perf_counter):
    """One coherent observation at the VBlank boundary plus its provenance.

    The core must already be paused. At most `attempts` bounded advances are
    made to reach the window; each is an exact RUN_DOTS count, so the returned
    dot is the endpoint's own completion dot, never a host estimate. The
    provenance reports how many dots the settling advances consumed, so the
    caller can still account for emulated time exactly.

    Acquisition, transport and decode are timed separately. The figures are
    whatever the run measured; they are not a contract.
    """
    log = record or (lambda entry: None)
    dot = None
    requests = 0
    transferred = 0
    advanced = 0
    boundary_seconds = 0.0
    read_seconds = 0.0
    decode_seconds = 0.0
    for _ in range(attempts):
        started = clock()
        lcd = client.read_lcd_status()
        requests += 1
        if not lcd['lcdc'] & 0x80:
            dot = _dots(client, PERIOD)
            requests += 1
            advanced += PERIOD
            boundary_seconds += clock() - started
            log({'event': 'boundary', 'reason': 'lcd-off', 'dots': PERIOD})
            continue
        ly = lcd['ly']
        if not BOUNDARY_FIRST <= ly <= BOUNDARY_LAST:
            count = ((BOUNDARY_FIRST - ly) % LINES) * LINE
            dot = _dots(client, count)
            requests += 1
            advanced += count
            boundary_seconds += clock() - started
            log({'event': 'boundary', 'reason': 'ly', 'ly': ly, 'dots': count})
            continue
        boundary_seconds += clock() - started
        started = clock()
        chunks = [(offset, client.peek_range('wram', offset, count)) for offset, count in binding.ranges]
        read_seconds += clock() - started
        requests += len(chunks)
        transferred += sum(len(data) for _offset, data in chunks)
        started = clock()
        observation = decode(binding, chunks)
        decode_seconds += clock() - started
        if observation['frame_pending']:
            started = clock()
            dot = _dots(client, LINE)
            requests += 1
            advanced += LINE
            boundary_seconds += clock() - started
            log({'event': 'boundary', 'reason': 'frame-pending', 'ly': ly, 'dots': LINE})
            continue
        started = clock()
        if dot is None:
            dot = client.read_host(abi.HOST_REG_DOT_LO) | (client.read_host(abi.HOST_REG_DOT_HI) << 32)
            requests += 2
        epoch = client.read_host(abi.HOST_REG_SNAPSHOT_EPOCH)
        requests += 1
        boundary_seconds += clock() - started
        provenance = {'dot': dot, 'epoch': epoch, 'ly': ly, 'stat_mode': lcd['mode'],
                      'boundary': 'vblank-complete', 'represents': 'logical',
                      'display_lag_frames': 1, 'requests': requests, 'bytes': transferred,
                      'advanced': advanced,
                      'decoder': observation['decoder'], 'rom_sha256': observation['rom_sha256'],
                      'timings': {'boundary_seconds': boundary_seconds,
                                  'read_seconds': read_seconds,
                                  'decode_seconds': decode_seconds,
                                  'state_seconds': boundary_seconds + read_seconds + decode_seconds}}
        return observation, provenance
    raise PlayFailure('STATE_BOUNDARY_UNREACHED')


class Strategy:
    """Observe, then choose one complete eight-button mask for the next update.

    Each decision starts from the fresh observation. The mask already sampled
    by the ROM is applied first, because it is committed to the next update;
    the mask chosen here is applied to the update after that. From that
    committed state the strategy rolls out each candidate direction under a
    continuation policy and keeps the direction that survives and travels
    furthest, then sends that direction's continuation mask.

    The continuation policy owns jump timing and releases. It presses A when
    the model says one more walking update would step off the ground, holds A
    while the jump is still rising, and releases it otherwise, so a later
    press registers as a fresh edge.

    The reference model is used to look ahead, never to supply state. Every
    rollout is seeded from observed bytes; a missing observation is an error.
    """
    # Candidate actions in preference order, each a direction and whether to
    # press A on the first update. Running right is the ordinary locomotion for
    # this level, so it is rolled out first and accepted as soon as it is safe
    # and gains ground; the rest are rolled out only when it is not, which is
    # what keeps an ordinary decision to a single rollout. The deliberate jumps
    # are how the player gets over the enemy, which no ground rule would do.
    ACTIONS = ((RIGHT | B, False), (RIGHT, False), (RIGHT | B, True),
               (RIGHT, True), (0, False), (LEFT, False), (0, True))
    HORIZON = 100
    PROGRESS = 8
    DEAD = -10 ** 9
    WON_SCORE = 10 ** 9
    # Read-only world knowledge: the enemy patrols 240..296, so its box can
    # reach any player box overlapping this band.
    BAND = (240 - 8, 296 + 8)

    def __init__(self, horizon=None):
        self.motion, self.power = _models()
        self.horizon = horizon or self.HORIZON

    def continuation(self, world, direction):
        """The complete mask this policy holds at `world` for one direction."""
        player = world.player
        if player.jump == 1:
            return direction | A           # still rising: hold for the long jump
        if not player.grounded:
            return direction & ~A          # descending: release so A can press again
        walked = self.power.update(world, direction & ~A)
        if not walked.player.grounded and walked.player.jump == 3:
            return direction | A           # one more walking update steps off the edge
        return direction & ~A

    def _rollout(self, base, direction, jump=False):
        """Follow one candidate under the continuation policy and score the end.

        `jump` presses A on the first update only; the continuation then holds
        it through the ascent and releases it, so the jump is a single edge.
        """
        world = base
        for step in range(self.horizon):
            mask = self.continuation(world, direction)
            if step == 0 and jump and world.player.grounded:
                mask = direction | A
            world = self.power.update(world, mask)
            if world.mode == WON:
                return self.WON_SCORE - step
            if world.mode in (RETRY, PAUSED, TIMEUP, OVER) or world.player.fell:
                return self.DEAD
        x = world.player.x // UNIT
        if (world.alive and self.BAND[0] < x < self.BAND[1]
                and x - base.player.x // UNIT < 4):
            # Standing still inside the patrol band is never safe: the enemy
            # arrives eventually, which can be beyond this horizon.
            return self.DEAD // 2 + x
        return x

    def choose(self, observation):
        mode = observation['mode']
        sampled = observation['buttons']['sampled']
        if mode == TITLE:
            # Start must arrive as an edge; hold it only until it is sampled.
            return (START, 1, 'start') if not sampled & START else (0, 1, 'start-sampled')
        if mode in (RETRY, WON, PAUSED, TIMEUP, OVER):
            return (START, 1, 'restart') if not sampled & START else (0, 1, 'restart-sampled')
        # The sampled mask is already committed to the next update; plan from it.
        base = self.power.update(to_world(observation), sampled)
        reach = base.player.x // UNIT + self.PROGRESS
        best, best_score = None, None
        for action in self.ACTIONS:
            score = self._rollout(base, *action)
            if best is None or score > best_score:
                best, best_score = action, score
            if score >= reach:
                break
        if best_score <= self.DEAD // 2:
            raise PlayFailure('STATE_NO_SAFE_ACTION')
        direction, jump = best
        mask = self.continuation(base, direction)
        if jump and base.player.grounded:
            mask = direction | A
        return mask, 1, 'lookahead:%s%d' % ('jump ' if jump else '', best_score)


def aligned_pair(client, binding, *, record=None, clock=time.perf_counter):
    """One observation and the actual frame that was drawn from it.

    The frame completed at a boundary is the one prepared from the previous
    boundary's state, so this observes, advances exactly one frame, and takes
    the snapshot there. The returned snapshot is the actual-pixel counterpart
    of the returned observation, which is what an aligned comparison needs.

    The snapshot fetch is timed here rather than at each call site, so the
    actual-pixel path reports its cost wherever it is used.
    """
    observation, provenance = observe(client, binding, record=record)
    _dots(client, PERIOD)
    after, after_provenance = observe(client, binding, record=record)
    _check_advance((observation, provenance), (after, after_provenance), 1,
                   observation['buttons']['sampled'])
    started = clock()
    metadata, packed = client.snapshot()
    snapshot_seconds = clock() - started
    return {'observation': observation, 'provenance': provenance,
            'next_provenance': after_provenance, 'metadata': metadata,
            'snapshot_seconds': snapshot_seconds}, packed


class Checkpoints:
    """Name the first observation that is an example of each comparison state.

    The five states the aligned comparison covers: the title and start, a jump,
    the camera scrolling, a dynamic object or power change, and completion.
    Each is claimed once, by the first observation that matches it.
    """
    NAMES = ('title', 'completion', 'dynamic', 'camera', 'movement')
    DYNAMIC = ('blocks', 'power', 'items')

    def __init__(self):
        self.seen = []
        self.previous = None

    @staticmethod
    def _changed(before, after):
        if before['enemy']['alive'] != after['enemy']['alive']:
            return True
        return any(before[field] != after[field] for field in Checkpoints.DYNAMIC)

    def classify(self, observation):
        previous, self.previous = self.previous, observation
        if observation['mode_name'] == 'TITLE':
            name = 'title'
        elif observation['mode_name'] == 'WON':
            name = 'completion'
        elif previous is None:
            return None
        elif self._changed(previous, observation):
            name = 'dynamic'
        elif observation['camera'] != previous['camera']:
            name = 'camera'
        elif observation['player']['jump']:
            name = 'movement'
        else:
            return None
        if name in self.seen:
            return None
        self.seen.append(name)
        return name

    def missing(self):
        return [name for name in self.NAMES if name not in self.seen]


def apply_mask(client, mask):
    if type(mask) is not int or not 0 <= mask <= 255:
        raise PlayFailure('STATE_MASK')
    client.write_host(abi.HOST_REG_INPUT, mask)
    if client.read_host(abi.HOST_REG_INPUT_EFFECTIVE) != mask:
        raise PlayFailure('STATE_INPUT')


def finish(client, result):
    """A PASS requires observed paused/neutral state and a certain session."""
    result['released'] = False
    if client.uncertain:
        result['status'] = 'FAIL'
        result.setdefault('reason', 'STATE_EXIT_UNCERTAIN')
        result['cleanup'] = {'verified': False, 'reason': 'uncertain; no further traffic'}
    else:
        try:
            client.control('HALT')
            apply_mask(client, 0)
            state = client.read_host(abi.HOST_REG_STATE)
            if state != abi.STATE_PAUSED:
                raise PlayFailure('STATE_EXIT_NOT_PAUSED')
            result['released'] = True
            result['cleanup'] = {'verified': True, 'state': state, 'input_effective': 0}
        except Exception as failure:
            result['status'] = 'FAIL'
            result.setdefault('reason', str(failure))
            result['release_error'] = str(failure)
            result['cleanup'] = {'verified': False, 'reason': str(failure)}
    result['uncertain'] = client.uncertain
    result['sequence'] = client.sequence


def play(client, image, binding, strategy=None, *, budget=None, record=None, retain=None,
         capture=None, require_title=True, start_delay_frames=0, clock=time.monotonic):
    """Run from RESET and the title to WON within the declared budget.

    Returns a result record; a failed attempt is reported, never retried
    beyond `budget['retries']`. On certain completion the input is released
    and the core left paused; after an uncertain completion no further traffic
    is sent.

    `capture(client, previous, previous_provenance, current, current_provenance)`
    runs at each boundary after the advance is checked. It is how a caller
    takes the aligned actual frame: the snapshot available at this boundary is
    the one drawn from `previous`.
    """
    limits = dict(BUDGET, **(budget or {}))
    if (type(start_delay_frames) is not int or start_delay_frames < 0
            or start_delay_frames > min(limits['frames'], limits['actions'])):
        raise PlayFailure('STATE_START_DELAY')
    strategy = strategy or Strategy()
    log = record or (lambda entry: None)
    keep = retain or (lambda step, observation, provenance: None)
    started = clock()
    result = {'status': 'FAIL', 'budget': limits, 'actions': [], 'frames': 0, 'attempts': 1,
              'observations': 0}
    observation = provenance = None
    try:
        result['identity'] = client.identify()
        result['load'] = client.load(image)
        client.select_input_source(abi.INPUT_SOURCE_UART)
        if client.read_host(abi.HOST_REG_INPUT_SOURCE) != abi.INPUT_SOURCE_UART:
            raise PlayFailure('STATE_SOURCE')
        apply_mask(client, 0)
        client.control('RESET')
        if client.read_host(abi.HOST_REG_STATE) != abi.STATE_PAUSED:
            client.control('HALT')
        observation, provenance = observe(client, binding, record=log)
        result['observations'] += 1
        keep(0, observation, provenance)
        if require_title and observation['mode'] != TITLE:
            # The demonstration runs the normal start path. A fixture that
            # begins mid-level says so explicitly rather than being tolerated.
            raise PlayFailure('STATE_START_NOT_TITLE')
        if start_delay_frames and observation['mode'] != TITLE:
            raise PlayFailure('STATE_START_NOT_TITLE')
        result['reset_epoch'] = provenance['epoch']
        result['start_delay_frames'] = start_delay_frames
        delay_remaining = start_delay_frames
        best_x, progress_frame = observation['player']['x'], 0
        while True:
            if len(result['actions']) >= limits['actions']:
                raise PlayFailure('STATE_BUDGET_ACTIONS')
            if result['frames'] >= limits['frames']:
                raise PlayFailure('STATE_BUDGET_FRAMES')
            if clock() - started > limits['wall_seconds']:
                raise PlayFailure('STATE_BUDGET_WALL')
            loop_started = clock()
            if delay_remaining:
                mask, frames, reason = 0, 1, 'start-delay'
                delay_remaining -= 1
            else:
                mask, frames, reason = strategy.choose(observation)
            decided = clock()
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
            if capture is not None:
                capture(client, before[0], before[1], observation, provenance)
            step = len(result['actions'])
            result['actions'].append({
                'step': step, 'mask': mask, 'frames': frames, 'reason': reason,
                'dot': provenance['dot'], 'timer': observation['timer'],
                'mode': observation['mode_name'], 'x': observation['player']['pixel_x'],
                'y': observation['player']['pixel_y'], 'enemy_x': observation['enemy']['pixel_x'],
                'loop_seconds': round(clock() - loop_started, 6),
                'decide_seconds': round(decided - loop_started, 6),
                **{name: round(value, 6)
                   for name, value in provenance['timings'].items()}})
            keep(step + 1, observation, provenance)
            if observation['player']['x'] > best_x:
                best_x, progress_frame = observation['player']['x'], result['frames']
            elif result['frames'] - progress_frame > limits['no_progress_frames']:
                raise PlayFailure('STATE_NO_PROGRESS')
            if observation['mode'] == WON:
                if capture is not None:
                    # The frame drawn from the winning state completes at the
                    # next boundary, so reach it before the run ends.
                    if result['frames'] >= limits['frames']:
                        raise PlayFailure('STATE_BUDGET_FRAMES')
                    final = observation, provenance
                    _dots(client, PERIOD)
                    observation, provenance = observe(client, binding, record=log)
                    result['frames'] += 1
                    _check_advance(final, (observation, provenance), 1, mask)
                    capture(client, final[0], final[1], observation, provenance)
                result['status'] = 'PASS'
                break
            if observation['mode'] == RETRY and not observation['buttons']['sampled'] & START:
                if result['attempts'] > limits['retries']:
                    raise PlayFailure('STATE_RETRY')
                result['attempts'] += 1
                best_x, progress_frame = 0, result['frames']
    except Exception as failure:
        result['reason'] = str(failure)
    finally:
        result['uncertain'] = client.uncertain
        result['sequence'] = client.sequence
        result['final'] = None if observation is None else {
            'mode': observation['mode_name'], 'timer': observation['timer'],
            'x': observation['player']['pixel_x'], 'dot': provenance['dot']}
        finish(client, result)
        elapsed = clock() - started
        if elapsed > limits['wall_seconds']:
            result['status'] = 'FAIL'
            result.setdefault('reason', 'STATE_BUDGET_WALL')
        result['wall_seconds'] = round(elapsed, 3)
    return result


def _check_advance(before, after, frames, mask):
    (observation, provenance), (observation2, provenance2) = before, after
    settled = provenance2.get('advanced', 0)
    # Without a settling advance the phase must be identical. With one, the
    # reader moved the core deliberately and reports exactly how far, so the
    # dot check still holds the run to an exact emulated time.
    if not settled and provenance2['ly'] != provenance['ly']:
        raise PlayFailure('STATE_PHASE_DRIFT')
    if provenance2['dot'] - provenance['dot'] != frames * PERIOD + settled:
        raise PlayFailure('STATE_DOT_DRIFT')
    if provenance2['epoch'] != provenance['epoch']:
        raise PlayFailure('STATE_EPOCH_CHANGED')
    updates = frames + (settled + PERIOD - 1) // PERIOD
    delta = (observation2['timer'] - observation['timer']) & 0xFFFF
    applied = observation['buttons']['sampled'] | mask
    reset = (observation2['mode'] == PLAYING
             and ((observation['mode'] in (RETRY, TIMEUP, WON, OVER) and applied & START)
                  or (observation['mode'] == PAUSED and applied & 64)))
    # Stage entry resets GameTimer. Other advances must remain monotonic.
    if (observation2['timer'] > updates if reset else delta > updates):
        raise PlayFailure('STATE_TIMER_DRIFT')
    steady = observation['mode'] == PLAYING and observation2['mode'] == PLAYING
    if (steady and not settled
            and not (observation['buttons']['sampled'] | mask) & START and delta != frames):
        raise PlayFailure('STATE_TIMER_DRIFT')
