"""Exact visible-window flow route, using ordinary public UART operations."""
from dataclasses import asdict
import json
from pathlib import Path
import time
import zlib

from n2m import generated_interfaces as abi
from flow_physical_reference import PERIOD, plan, schedule, expected_snapshot

DOT_HZ = 4194304


def run(client, rom, folder, log, expected_build, prior, lcd, mode,
        *, renderer=None, sleep=time.sleep):
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

    def pause_at(frame):
        # Aim early in the broad visible interval. Sleep is only pacing; the
        # returned HALT dot must prove the intended sample window was reached.
        start = lcd+frame*PERIOD+4096
        end = lcd+frame*PERIOD+60000
        for _ in range(6):
            current = dot()
            assert current < end, 'FLOW_MISSED_WINDOW'
            if current >= start:
                return current
            client.control('RUN')
            sleep(max(.001, (start-current)/DOT_HZ-.003))
            returned = client.control('HALT')['dot']
            assert dot() == returned, 'FLOW_HALT_DOT'
        raise AssertionError('FLOW_WINDOW_PROGRESS')

    try:
        assert client.sequence == prior['sequence'], 'FLOW_SESSION_CHANGED'
        identity = client.identify()
        assert identity['build_id'] == expected_build == prior['build_id'], 'FLOW_BUILD_ID'
        safe()
        assert reg('IMAGE_VALID') == 1 and dot() == prior['halt_dot'], 'FLOW_PRIOR_STATE'
        old, _ = client.snapshot()
        previous = prior['frame']
        assert (old['epoch'], old['seq'], old['dot']) == (
            previous['epoch'], previous['sequence'], previous['dot']), 'FLOW_PRIOR_FRAME'
        epoch = (previous['epoch']+2) % 2**32
        armed = True
        loaded = client.load(rom)
        safe()
        assert dot() == 0, 'FLOW_LOAD_DOT'
        for frame, task in sorted(tasks.items()):
            paused = pause_at(frame)
            if 'buttons' in task:
                value = task['buttons']
                applied = client.control('INPUT', value)['dot']
                assert applied == paused, 'FLOW_APPLIED_DOT'
                events.append((applied, value))
                mask = value
                log(dict(kind='applied', dot=applied, buttons=value, sample_update=frame+1))
            if 'capture' in task:
                number = task['capture']
                expected_frame = number+1
                metadata, packed = client.snapshot()
                state, wanted = expected_snapshot(metadata, expected_frame, events,
                                                  epoch, lcd, renderer)
                pixels = bytes((value >> shift) & 3 for value in packed for shift in (0, 2, 4, 6))
                assert len(pixels) == len(wanted) == 23040, 'FLOW_FRAME_SIZE'
                name = f'update-{number:03d}'
                (folder/f'{name}.2bpp').write_bytes(packed)
                mismatches = sum(a != b for a, b in zip(pixels, wanted))
                assert not mismatches, f'FLOW_PIXELS update={number} mismatches={mismatches}'
                safe()
                record = dict(name=name, logical_update=number, metadata=metadata,
                              state=asdict(state), pixels=23040,
                              crc32=f'{zlib.crc32(pixels):08x}')
                checks.append(record)
                log(dict(kind='checkpoint', **record))
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
