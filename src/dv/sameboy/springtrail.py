"""Validate complete native framebuffer/input output; no DUT observations."""
import hashlib
import json
from pathlib import Path
import zlib


def compare_game_images(data, count):
    """Fixed callback/state mapping, from the script and approved display delay."""
    import sys
    names = ('interactions_reference', 'movement_reference', 'reference',
             'flow_frames', 'scene_reference', 'scene_art')
    saved = {name: sys.modules.get(name) for name in names}
    old_path = sys.path[:]
    try:
        for name in saved:
            sys.modules.pop(name, None)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'springtrail'))
        from interactions_reference import Game, update
        from flow_frames import image
    finally:
        sys.path[:] = old_path
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    state = Game()
    expected = [bytes(23040)]*3 + [image(state)]
    for index in range(count-2):
        state = update(state, 129 if index == 0 else 1)
        expected.append(image(state))
    assert len(data) == len(expected)*23040, 'REFERENCE_GAME_LENGTH'
    for index, want in enumerate(expected):
        actual = data[index*23040:(index+1)*23040]
        mismatch = next((p for p,(a,b) in enumerate(zip(actual,want)) if a != b), None)
        assert mismatch is None, f'REFERENCE_GAME_PIXELS frame={index} index={mismatch}'


def check(folder, contract, case):
    rows = [json.loads(line) for line in (folder/'observations.log').read_text().splitlines()]
    assert rows and rows[-1]['kind'] == 'end', 'REFERENCE_END'
    frames, inputs, last_dot = [], [], -1
    for row in rows[:-1]:
        assert row['kind'] in ('frame', 'input'), 'REFERENCE_RECORD'
        assert type(row['dot']) is int and row['dot'] > last_dot, 'REFERENCE_ORDER'
        last_dot = row['dot']
        if row['kind'] == 'input':
            index = len(inputs)
            assert index < len(contract['inputs']) and row['index'] == index, 'REFERENCE_INPUT_COUNT'
            expected = contract['inputs'][index]
            assert expected['dot'] <= row['dot'] <= expected['dot']+contract['input_lateness_max'], 'REFERENCE_INPUT_TIME'
            assert row['buttons'] == expected['buttons'], 'REFERENCE_INPUT_MASK'
            inputs.append(row)
        else:
            assert row['index'] == len(frames), 'REFERENCE_FRAME_INDEX'
            frames.append(row)
    count = contract['cases'][case]
    assert len(frames) == count+2 and [f['type'] for f in frames] == [1, 2]+[0]*count, 'REFERENCE_FRAME_COUNT'
    assert len(inputs) == len(contract['inputs']), 'REFERENCE_INPUT_MISSING'
    end = rows[-1]
    assert end == dict(kind='end', frames=count+2, normal_frames=count, inputs=len(inputs), dot=end['dot']), 'REFERENCE_END_COUNTS'
    assert last_dot <= end['dot'] <= contract['dot_bound'], 'REFERENCE_PROGRESS'
    data = (folder/'frames.shades').read_bytes()
    size = contract['frame_bytes']
    assert len(data) == len(frames)*size and all(v < 4 for v in data), 'REFERENCE_FRAME_BYTES'
    assert data[:size] == bytes(size), 'REFERENCE_BLANK_FRAME'
    assert frames[0]['mode'] == 0 and frames[-1]['mode'] == 1, 'REFERENCE_GAME_FLOW'
    if 'settled' in case:
        assert [f['buttons'] for f in frames] == [0,0,0,129]+[1]*(count-2), 'REFERENCE_GAME_BUTTONS'
        compare_game_images(data, count)
    ledger = []
    for i, row in enumerate(frames):
        image = data[i*size:(i+1)*size]
        ledger.append(dict(**row, offset=i*size, size=size,
                           sha256=hashlib.sha256(image).hexdigest(), crc32=f'{zlib.crc32(image):08x}'))
    return dict(frames=ledger, inputs=inputs, end=end)
