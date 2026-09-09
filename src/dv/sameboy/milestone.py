"""Fixed Springtrail milestone contract and independent native frame checks."""
from pathlib import Path
import sys


def models():
    names = ('milestone', 'interaction_routes', 'interactions_reference',
             'movement_reference', 'flow_frames', 'reference', 'scene_art', 'scene_reference')
    saved = {name: sys.modules.get(name) for name in names}
    path = sys.path[:]
    try:
        for name in names:
            sys.modules.pop(name, None)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'springtrail'))
        from milestone import plan
        from interactions_reference import Game, update
        from flow_frames import image
        return plan, Game, update, image
    finally:
        sys.path[:] = path
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def contract(original, case):
    plan, *_ = models()
    schedule = plan(case.endswith('-short'))
    assert schedule['image_sha256']==original['settled_image']['sha256'], 'MILESTONE_ROM_IDENTITY'
    return dict(original, milestone=schedule, inputs=schedule['inputs'],
                cases={case:schedule['normal_frames']},
                end_dot=schedule['end_dot'], dot_bound=schedule['end_dot']+24)


def check_frames(frames, data, schedule):
    _, Game, update, image = models()
    states = [Game()]
    for event in schedule['inputs']:
        states.append(update(states[-1], event['buttons']))
    # Prefix LCD-off/artificial and first normal blank precede three title
    # images. Every following image is one fixed scripted state, in order.
    for index, row in enumerate(frames):
        state = states[max(0,index-5)]
        want = bytes(23040) if index<3 else image(state)
        actual = data[index*23040:(index+1)*23040]
        assert actual == want, f'MILESTONE_PIXELS callback={index}'
        sampled = 0 if index<5 else schedule['inputs'][index-5]['buttons']
        assert row['buttons']==sampled, f'MILESTONE_BUTTONS callback={index}'
        assert row['mode']==states[max(0,index-4)].mode, f'MILESTONE_MODE callback={index}'
    assert all(b['dot']-a['dot']==70224 for a,b in zip(frames[2:],frames[3:])), 'MILESTONE_FRAME_PERIOD'
