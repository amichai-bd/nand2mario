"""Exact visible-window flow route, using ordinary public UART operations."""
from dataclasses import asdict
import json
import hashlib
from pathlib import Path
import time
import zlib

from n2m import generated_interfaces as abi
from flow_physical_reference import PERIOD, STAGES, plan, schedule, predict, expected_snapshot
from interactions_reference import PLAYING, PAUSED, WON, RETRY

DOT_HZ = 4194304


def run(client, rom, folder, log, expected_build, prior, lcd, mode,
        *, renderer=None, sleep=time.sleep, clock=time.monotonic):
    """Caller owns verified setup, immutable package, session and300s supervisor."""
    folder = Path(folder)
    segments, captures = plan(mode)
    changes, count = schedule(segments)
    tasks = {}
    for frame, buttons in changes:
        tasks.setdefault(frame, {})['buttons'] = buttons
    if mode == 'feasibility':
        # Exercise the same adjacent-frame control boundary without starting
        # gameplay. This is a timing diagnostic, not either acceptance route.
        for frame in range(8):
            tasks.setdefault(frame, {})['buttons'] = 0
    for number in captures:
        tasks.setdefault(number+2, {})['capture'] = number
    events, checks = [], []
    armed = completed = False
    mask = 0

    def reg(name):
        return client.read_host(getattr(abi, 'HOST_REG_'+name))

    def dot():
        high, low = reg('DOT_HI'), reg('DOT_LO')
        assert high == reg('DOT_HI'), 'FLOW_DOT_ROLLOVER'
        return high*2**32+low

    def safe():
        assert reg('STATE') == abi.STATE_PAUSED, 'FLOW_PAUSED'
        assert reg('INPUT_SOURCE') == abi.INPUT_SOURCE_UART, 'FLOW_UART_SOURCE'
        assert reg('INPUT') == reg('INPUT_EFFECTIVE') == mask, 'FLOW_INPUT_MASK'

    def pause_at(frame, late=0):
        # Aim early in the broad visible interval. Sleep is only pacing; the
        # returned HALT dot must prove the intended sample window was reached.
        start = lcd+frame*PERIOD+4096
        end = lcd+(frame+late)*PERIOD+60000
        for _ in range(6):
            current = dot()
            assert current < end, 'FLOW_MISSED_WINDOW'
            if current >= start:
                phase = (current-lcd) % PERIOD
                if 4096 <= phase < 60000:
                    return current
                start = lcd+((current-lcd)//PERIOD+1)*PERIOD+4096
            began = clock()
            client.control('RUN')
            run_elapsed = clock()-began
            requested_sleep = max(0, (start-current)/DOT_HZ-run_elapsed)
            sleep(requested_sleep)
            halt_began = clock()
            returned = client.control('HALT')['dot']
            halt_elapsed = clock()-halt_began
            log(dict(kind='pacing', frame=frame, start=start, end=end,
                     before_dot=current, halt_dot=returned, advance=returned-current,
                     run_seconds=run_elapsed, sleep_seconds=requested_sleep,
                     halt_seconds=halt_elapsed, elapsed_seconds=clock()-began))
            assert dot() == returned, 'FLOW_HALT_DOT'
        raise AssertionError('FLOW_WINDOW_PROGRESS')

    def capture(name, paused, first, last):
        # Public paused time selects a source frame inside a frozen interval.
        # Snapshot metadata confirms it; neither metadata nor pixels pick state.
        visible_frame = (paused-lcd)//PERIOD
        assert first <= visible_frame <= last, 'FLOW_CAPTURE_INTERVAL'
        expected_frame = visible_frame-1
        metadata, packed = client.snapshot()
        state, wanted = expected_snapshot(metadata, expected_frame, events, epoch, lcd, renderer)
        pixels = bytes((value >> shift) & 3 for value in packed for shift in (0, 2, 4, 6))
        assert len(pixels) == len(wanted) == 23040, 'FLOW_FRAME_SIZE'
        (folder/f'{name}.2bpp').write_bytes(packed)
        mismatches = sum(a != b for a, b in zip(pixels, wanted))
        assert not mismatches, f'FLOW_PIXELS {name} mismatches={mismatches}'
        safe()
        record = dict(name=name, logical_update=expected_frame-1, metadata=metadata,
                      state=asdict(state), pixels=23040, crc32=f'{zlib.crc32(pixels):08x}')
        checks.append(record)
        log(dict(kind='checkpoint', **record))
        return state

    try:
        assert client.sequence == prior['sequence'], 'FLOW_SESSION_CHANGED'
        identity = client.identify()
        assert identity['build_id'] == expected_build == prior['build_id'], 'FLOW_BUILD_ID'
        safe()
        assert reg('IMAGE_VALID') == 1 and dot() == prior['halt_dot'], 'FLOW_PRIOR_STATE'
        previous = prior['frame']
        assert reg('SNAPSHOT_VALID') == 1, 'FLOW_PRIOR_FRAME'
        assert (reg('SNAPSHOT_EPOCH'), reg('SNAPSHOT_SEQ_LO'), reg('SNAPSHOT_SEQ_HI')) == (
            previous['epoch'], previous['sequence'] & 0xffffffff,
            previous['sequence'] >> 32), 'FLOW_PRIOR_FRAME'
        old = client.read_storage('READ_FRAME', 5760)
        assert hashlib.sha256(old).hexdigest() == prior['snapshot_sha256'], 'FLOW_PRIOR_PIXELS'
        epoch = (previous['epoch']+2) % 2**32
        armed = True
        loaded = client.load(rom)
        safe()
        assert dot() == 0, 'FLOW_LOAD_DOT'
        for frame, task in sorted(tasks.items()):
            stable = mode != 'feasibility' and task.get('capture') == count
            late = 8 if stable else 0
            paused = pause_at(frame, late)
            if 'buttons' in task:
                value = task['buttons']
                applied = client.control('INPUT', value)['dot']
                assert applied == paused, 'FLOW_APPLIED_DOT'
                events.append((applied, value))
                mask = value
                log(dict(kind='applied', dot=applied, buttons=value, sample_update=frame+1))
            if 'capture' in task:
                number = task['capture']
                name = f'update-{number:03d}'
                state = capture(name, paused, frame, frame+late)
                if stable:
                    assert state.mode == (WON if mode == 'success' else RETRY), 'FLOW_TERMINAL_MODE'
                    assert state.score == (2 if mode == 'success' else 1), 'FLOW_TERMINAL_SCORE'
        if mode != 'feasibility':
            # Retry is forbidden until the terminal picture above is checked.
            stages = STAGES if mode == 'success' else STAGES[:1]
            for name, value in stages:
                before = predict((paused-lcd)//PERIOD+1, events, lcd)
                applied = client.control('INPUT', value)['dot']
                assert applied == paused, 'FLOW_STAGE_APPLIED_DOT'
                events.append((applied, value))
                mask = value
                log(dict(kind='applied', dot=applied, buttons=value, stage=name))
                target = (paused-lcd)//PERIOD+4
                paused = pause_at(target, 4)
                state = capture(name, paused, target, target+4)
                if name in ('pause', 'held-a', 'pause-again'):
                    assert state.mode == PAUSED and state.timer == before.timer, 'FLOW_PAUSE_FREEZE'
                    assert state.enemy_x == before.enemy_x and state.player.x == before.player.x, 'FLOW_PAUSE_POSITION'
                else:
                    assert state.mode == PLAYING, 'FLOW_STAGE_PLAYING'
                assert state.player.x == 24*16 and state.player.y == 112*16, 'FLOW_RESTART_POSITION'
                assert state.score == state.collected == 0, 'FLOW_RESTART_SCORE'
                if name in ('select-held', 'select-playing'):
                    assert state.timer > before.timer, 'FLOW_SELECT_IGNORED'
        final_applied = client.control('INPUT', 0)['dot']
        assert final_applied == dot(), 'FLOW_FINAL_APPLIED_DOT'
        events.append((final_applied, 0))
        log(dict(kind='applied', dot=final_applied, buttons=0, sample_update=None))
        mask = 0
        safe()
        assert not client.uncertain, 'FLOW_FINAL_CERTAINTY'
        result = dict(status='PASS', mode=mode, load=loaded, epoch=epoch, lcd=lcd,
                      planned_updates=count, events=events, checkpoints=checks,
                      final_dot=dot(), final_input=0, certain=True)
        (folder/'flow.json').write_text(json.dumps(result, indent=2)+'\n')
        completed = True
        return result
    finally:
        if armed and not completed and not client.uncertain:
            client.control('HALT')
            client.control('INPUT', 0)
