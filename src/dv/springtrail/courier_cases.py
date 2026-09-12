"""Current courier operands and approved-map output, without SM83 table imports."""
from power_frames import courier


def cases():
    result = [dict(name=f'pose-{pose}-{face}', pose=pose, left=face == 'left',
                   x=24, y=32, hidden=False, camera=0, project=False)
              for pose in range(18) for face in ('right', 'left')]
    edges = ((-16, 32), (-15, 32), (-8, -8), (-7, -7),
             (159, 143), (160, 144), (256, 32), (-264, 32))
    result += [dict(name=f'edge-{i}', pose=11, left=bool(i % 2), x=x, y=y,
                    hidden=False, camera=0, project=False)
               for i, (x, y) in enumerate(edges)]
    result += [dict(name=f'projection-{i}', pose=0, left=bool(i % 2), x=x, y=y,
                    hidden=False, camera=camera, project=True)
               for i, (x, y, camera) in enumerate(
                   ((4095, -1, 256), (-1, -1, 0), (4112, 511, 256), (0, 512, 256)))]
    result += [dict(name=f'hidden-{pose}', pose=pose, left=left, x=24, y=32,
                    hidden=True, camera=0, project=False)
               for pose, left in ((0, False), (17, True))]
    return result


def parts():
    rows = cases()
    return {'a': rows[:18], 'b': rows[18:36], 'c': rows[36:]}


def expected(case):
    x, y = case['x'], case['y']
    if case['project']:
        x, y = x // 16 - case['camera'], y // 16
    pieces = courier(case['pose'], case['left'], x, y, case['hidden'])
    assert len(pieces) in (16, 24)
    return pieces + bytes(160 - len(pieces))


def operands(case):
    """Only inputs are packaged into the CPU image."""
    def word(value):
        return [value & 255, (value >> 8) & 255]
    return bytes([case['pose'], 32 * case['left'], int(case['hidden']),
                  int(case['project']), *word(case['x']), *word(case['y']),
                  *word(case['camera'])])
