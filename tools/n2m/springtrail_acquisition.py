"""Bounded ordinary-input acquisition using the existing coherent play loop."""
from dataclasses import asdict, replace
from pathlib import Path
import time

from . import generated_interfaces as abi
from . import springtrail_play as player
from . import springtrail_state as reader
from .records import atomic_json, file_hash


class Route:
    def __init__(self, plan):
        route, = reader._import('thrower_route')
        _, model = reader._models()
        self.limit = route.LIMITS[plan]
        self.inputs = route.masks()[:self.limit] + [0,0]
        self.worlds = [model.World()]
        for mask in self.inputs:
            # PrepareMap consumes the dirty request before coherent acquisition.
            self.worlds.append(replace(model.update(self.worlds[-1],mask),block_dirty=0))
        self.checkpoints = {k:v for k,v in route.CHECKPOINTS.items() if k <= self.limit}
        self.issued = 0

    def check(self, observation, index):
        actual = asdict(reader.to_world(observation))
        expected = asdict(self.worlds[index])
        if actual != expected:
            field = next(k for k in expected if actual[k] != expected[k])
            raise player.PlayFailure(f'ACQUISITION_STATE update={index} field={field}')

    def choose(self, observation):
        self.check(observation,max(0,self.issued-1))
        if self.issued > self.limit:
            raise player.PlayFailure('ACQUISITION_ROUTE_EXHAUSTED')
        mask = self.inputs[self.issued]
        self.issued += 1
        return mask,1,'ordinary-acquisition'

    def complete(self, observation):
        self.check(observation,max(0,self.issued-1))
        return self.issued == self.limit+1


def run(client, image, binding, out, *, plan, write_png, budget=None, clock=time.monotonic):
    route = Route(plan)
    spec, = reader._import('thrower_route')
    renderer, = reader._import('entities_frames')
    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    captures, observed = [],[]
    captured = set()
    limits = dict(frames=route.limit+3,actions=route.limit+2,retries=0,
                  no_progress_frames=route.limit+2,wall_seconds=spec.CAPS[plan])
    limits.update(budget or {})

    def keep(index, observation, provenance):
        observed.append(dict(index=index,observation=observation,provenance=provenance))

    def capture(connection, previous, prior, current, now):
        # The final flush has no new issued action and represents the terminal
        # route state; ordinary callbacks represent the preceding observation.
        index = max(0,len(observed)-2)
        route.check(previous,index)
        if index not in route.checkpoints or index in captured:
            return
        name = route.checkpoints[index]
        meta, packed = connection.snapshot()
        if (meta['size'] != abi.FRAME_BYTES or len(packed) != abi.FRAME_BYTES
                or meta['epoch'] != prior['epoch']):
            raise player.PlayFailure('ACQUISITION_FRAME_IDENTITY')
        if (not prior['dot'] < meta['dot'] <= now['dot']
                or meta['dot'] != now['epoch_frame_dot']):
            raise player.PlayFailure('ACQUISITION_FRAME_COMPLETION')
        actual = bytes((byte >> shift)&3 for byte in packed for shift in (0,2,4,6))
        expected = renderer.image(route.worlds[index])
        path = out/f'{index:04d}-{name}.2bpp'
        path.write_bytes(packed)
        write_png(actual,out/f'{index:04d}-{name}-actual.png')
        if actual != expected:
            first = next(i for i,(a,b) in enumerate(zip(actual,expected)) if a != b)
            raise player.PlayFailure(f'ACQUISITION_PIXELS {name} pixel={first}')
        captures.append(dict(name=name,update=index,checked_pixels=23040,
                             metadata=meta,previous_dot=prior['dot'],capture_dot=now['dot'],
                             file=path.name,sha256=file_hash(path)))
        captured.add(index)

    result = player.play(client,image,binding,strategy=route,budget=limits,
                         retain=keep,capture=capture,complete=route.complete,clock=clock)
    result.update(plan=plan,source='independent fixed ordinary-input history',
                  captures=captures,expected_captures=list(route.checkpoints.values()))
    if result['status'] == 'PASS' and captured != set(route.checkpoints):
        result.update(status='FAIL',reason='ACQUISITION_CAPTURES_MISSING')
    atomic_json(out/'observations.json',observed)
    atomic_json(out/'acquisition.json',result)
    return result
