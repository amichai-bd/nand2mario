"""Historical #316 UART play; new composition requires its own frozen schedule."""
from dataclasses import replace
from pathlib import Path
import time

from n2m import generated_interfaces as abi
from n2m.records import atomic_json, file_hash
from interactions_reference import Game, PLAYING, PAUSED, RETRY, update
from flow_frames import image
from flow_reference import require_baseline_rom

# Historical #316 DMA-publisher ROM; #291 used its older producer/76964.
LCD, PERIOD, DOT_HZ = 81352, 70224, 4194304
CYCLE_SECONDS = 20


def expected(mode):
    game = replace(Game(), mode=PLAYING)
    if mode == RETRY:
        for _ in range(91):
            game = update(game, 49)
        assert (game.mode, game.player.x, game.player.y, game.player.camera,
                game.collected, game.score) == (RETRY, 3200, 2336, 128, 1, 1)
    else:
        game = replace(game, mode=mode)
    return image(game)


def check_pixels(packed, mode):
    assert len(packed) == 5760, 'ENDURANCE_FRAME_SIZE'
    pixels = bytes((b >> shift) & 3 for b in packed for shift in (0, 2, 4, 6))
    wanted = expected(mode)
    # Previous idle length changes the offscreen enemy's phase. At camera128
    # its complete possible patrol projection is x112..159, y120..127.
    indices = [i for i in range(23040) if not
               (mode == RETRY and 120 <= i//160 < 128 and i%160 >= 112)]
    mismatch = next((i for i in indices if pixels[i] != wanted[i]), None)
    assert mismatch is None, f'ENDURANCE_PIXELS mode={mode} pixel={mismatch}'
    return len(indices)


def run(client, rom, root, *, epoch, cycles, clock=time.monotonic, sleep=time.sleep):
    """One or90 fixed20s cycles, then three complete reset/load/start cycles."""
    require_baseline_rom(rom)
    assert cycles in (1, 90), 'ENDURANCE_PLAN'
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    log = []
    last = None
    mask = 0
    armed = False
    result = dict(status='FAIL', cycles=cycles, planned_seconds=cycles*CYCLE_SECONDS,
                  samples=[], lifecycles=[])

    def record(kind, **fields):
        row = dict(kind=kind, wall=clock(), **fields)
        log.append(row)
        atomic_json(root/'journal.json', log)

    def wide(low, high):
        # Live counters can cross32 bits during30minutes; no torn low/high read.
        for _ in range(3):
            first = client.read_host(high)
            value = client.read_host(low)
            if first == client.read_host(high):
                return (first << 32) | value
        raise AssertionError('ENDURANCE_COUNTER_ROLLOVER')

    def public(running):
        state = dict(dot=wide(abi.HOST_REG_DOT_LO, abi.HOST_REG_DOT_HI),
                     retired=wide(abi.HOST_REG_RETIRE_LO, abi.HOST_REG_RETIRE_HI))
        assert client.read_host(abi.HOST_REG_STATE) == (abi.STATE_RUNNING if running else abi.STATE_PAUSED), 'ENDURANCE_STATE'
        assert client.read_host(abi.HOST_REG_IMAGE_VALID) == 1, 'ENDURANCE_IMAGE'
        assert client.read_host(abi.HOST_REG_INPUT_SOURCE) == abi.INPUT_SOURCE_UART, 'ENDURANCE_SOURCE'
        assert client.read_host(abi.HOST_REG_INPUT) == client.read_host(abi.HOST_REG_INPUT_EFFECTIVE) == mask, 'ENDURANCE_INPUT'
        return state

    def buttons(value):
        nonlocal mask
        before = wide(abi.HOST_REG_DOT_LO, abi.HOST_REG_DOT_HI)
        reply = client.control('INPUT', value)
        after = wide(abi.HOST_REG_DOT_LO, abi.HOST_REG_DOT_HI)
        assert before <= reply['dot'] <= after, 'ENDURANCE_INPUT_DOT'
        mask = value
        record('input', mask=mask, applied_dot=reply['dot'], before=before, after=after)
        return reply['dot']

    def capture(name, mode, running, after=0):
        nonlocal last
        before = public(running)
        meta, packed = client.snapshot()
        frontier = public(running)
        assert meta['epoch'] == epoch, 'ENDURANCE_EPOCH'
        assert meta['size'] == 5760, 'ENDURANCE_FRAME_SIZE'
        row = LCD+meta['seq']*PERIOD+143*456
        assert row <= meta['dot'] < row+456, 'ENDURANCE_FRAME_DOT'
        assert after <= meta['dot'] <= frontier['dot'], 'ENDURANCE_SAMPLE_TIME'
        # Snapshot acquisition is latest-frame convenience, not all-frame proof.
        assert before['dot']-meta['dot'] < 2*PERIOD, 'ENDURANCE_STALE_SAMPLE'
        if last is not None:
            assert meta['seq'] > last['seq'] and meta['dot'] > last['dot'], 'ENDURANCE_FRAME_PROGRESS'
        count = check_pixels(packed, mode)
        path = root/(name+'.2bpp')
        path.write_bytes(packed)
        row = dict(name=name, mode=mode, metadata=meta, checked_pixels=count,
                   file=path.name, sha256=file_hash(path), before=before, frontier=frontier)
        result['samples'].append(row)
        record('sample', **row)
        last = meta
        return frontier

    def advance(target):
        current = public(False)['dot']
        while current < target:
            amount = min(PERIOD, target-current)
            reply = client.run_dots(amount)
            assert reply == dict(dot=current+amount, executed=amount, reason=abi.WIRE_RUN_DOTS_COUNT), 'ENDURANCE_COUNT'
            current += amount
        assert current == target, 'ENDURANCE_START_DOT'

    def start(name, reset):
        nonlocal epoch, last, mask, armed
        if reset:
            client.control('RESET')
            epoch += 1
        armed = True
        receipt = client.load(rom)
        epoch += 2
        last = None
        buttons(0)
        assert public(False)['dot'] == 0, 'ENDURANCE_LOAD_DOT'
        advance(LCD+2*PERIOD+4096)
        capture(name+'-title', 0, False)
        buttons(128)
        advance(LCD+3*PERIOD+4096)
        buttons(0)
        advance(LCD+5*PERIOD+4096)
        capture(name+'-play', PLAYING, False)
        record('lifecycle', name=name, epoch=epoch, receipt=receipt)
        return receipt

    try:
        result['initial_load'] = start('origin', False)
        first = public(False)
        client.control('RUN')
        began = clock()  # Reply is after RUN; this conservative origin cannot overclaim duration.
        record('continuous_start', dot=first['dot'])
        previous = first
        for index in range(cycles):
            deadline = began+(index+1)*CYCLE_SECONDS
            assert clock() < began+index*CYCLE_SECONDS+1, 'ENDURANCE_SCHEDULE_LATE'
            applied = buttons(49)
            sleep(3)
            current = capture(f'{index:03d}-retry', RETRY, True, applied+120*PERIOD)
            assert current['dot'] > previous['dot'] and current['retired'] > previous['retired'], 'ENDURANCE_PROGRESS'
            applied = buttons(128)
            sleep(.1)
            capture(f'{index:03d}-restart', PLAYING, True, applied+3*PERIOD)
            buttons(0)
            if index == 0:
                sleep(.1)
                applied = buttons(128)
                sleep(.1)
                capture('pause', PAUSED, True, applied+3*PERIOD)
                buttons(0)
                sleep(.1)
                applied = buttons(128)
                sleep(.1)
                capture('resume', PLAYING, True, applied+3*PERIOD)
                buttons(0)
            assert clock() < deadline, 'ENDURANCE_CYCLE_BUDGET'
            sleep(max(0, deadline-clock()))
            previous = current
        # One second accommodates crystal/host clock phase without shortening
        # either physical duration or the independently checked emulated duration.
        sleep(1)
        final_live = capture('continuous-final', PLAYING, True)
        elapsed = clock()-began
        assert elapsed >= cycles*CYCLE_SECONDS, 'ENDURANCE_DURATION'
        assert final_live['dot']-first['dot'] >= cycles*CYCLE_SECONDS*DOT_HZ, 'ENDURANCE_DOT_DURATION'
        halted = client.control('HALT')
        record('continuous_end', elapsed=elapsed, halt=halted, frontier=final_live)
        result.update(continuous_seconds=elapsed, continuous_dot_delta=final_live['dot']-first['dot'])
        buttons(0)
        for index in range(3):
            result['lifecycles'].append(start(f'cycle-{index+1}', True))
        assert len(result['lifecycles']) == 3, 'ENDURANCE_LIFECYCLE_COUNT'
        result['status'] = 'PASS'
    except BaseException as error:
        result.update(status='FAIL', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        try:
            if armed and not client.uncertain:
                client.control('HALT')
                buttons(0)
                result['final'] = public(False)
                result['epoch'] = epoch
            elif armed:
                raise RuntimeError('ENDURANCE_UNCERTAIN_CLEANUP')
        except BaseException as error:
            result.update(status='FAIL', cleanup_error=f'{type(error).__name__}: {error}')
            raise
        finally:
            result['uncertain'] = client.uncertain
            result['next_sequence'] = client.sequence
            atomic_json(root/'result.json', result)
    return result
