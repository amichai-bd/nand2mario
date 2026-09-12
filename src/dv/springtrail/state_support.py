"""Shared fixtures for the Springtrail state reader and player tests.

Every fixture state is produced by the reference model, so it is a state the
ROM can actually hold. Hand-written records are not used: the decoder checks
cross-field invariants, and an unreachable record would fail them for the wrong
reason.

The image is built in this process from current sources, the same way
`startup_anchor` does, so a fixture costs the same whether or not a tagged
build happens to be lying around. `package` is the separate, slower path for
the one test that exercises `bind_package` against an immutable attempt.
"""
import glob
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from n2m import generated_interfaces as abi  # noqa: E402
from n2m import springtrail_state as state  # noqa: E402
from state_fake import reachable, wram_image  # noqa: E402
from progress_reference import PLAYING
from entities_reference import update as model_update  # noqa: E402

ROM_SHA256 = next(iter(state.SUPPORTED))
SOURCE = ROOT / 'src/sw/springtrail'
TAG = 'sptest'
_CACHE = {}


def build():
    """The current image and its linked symbols, assembled in this process."""
    if 'build' not in _CACHE:
        prior = sys.path[:]
        try:
            sys.path.insert(0, str(ROOT / 'tools'))
            from sw.assembler import assemble
            from sw.assets import encode_shades, load_shades
            from sw.linker import link
            from sw.package import package as package_image
        finally:
            sys.path[:] = prior
        target = json.loads((ROOT / 'src/sw/targets.json').read_text())['targets']['springtrail']
        assets = {name: encode_shades(load_shades(SOURCE / spec['source'], spec['source']),
                                      spec['source'])
                  for name, spec in target['assets'].items()}
        obj = assemble(SOURCE / 'main.asm', SOURCE,
                       ROOT / 'src/sw/generated/interfaces.inc', assets)
        linked = link([('main.asm', obj)],
                      json.loads((SOURCE / target.get('layout', 'layout.json')).read_text()),
                      target['entry'])
        image = package_image(linked, target['title'], target['version'], target['profile'])
        symbols = {entry['symbol']: entry['value'] for entry in linked['symbols']['symbols']
                   if entry.get('unit') == 'main.asm' and isinstance(entry.get('value'), int)}
        _CACHE['build'] = (bytes(image), symbols)
    return _CACHE['build']


def binding():
    """(image, Binding) for the image the repository builds from current sources."""
    image, symbols = build()
    return image, state.Binding(hashlib.sha256(image).hexdigest(), symbols)


def package(tag=TAG):
    """An immutable tagged sw/build attempt, built once per process if needed."""
    if tag not in _CACHE:
        pattern = str(ROOT / f'workdir/builds/{tag}/sw/build/springtrail/runs/*/result.json')
        found = glob.glob(pattern)
        if not found:
            subprocess.run([sys.executable, str(ROOT / 'tools/build.py'), 'sw', 'build',
                            'springtrail', '--tag', tag, '--json'], cwd=ROOT, check=True,
                           stdout=subprocess.DEVNULL)
            found = glob.glob(pattern)
        manifest = next(p for p in found if json.loads(Path(p).read_text())['status'] == 'PASS')
        _CACHE[tag] = Path(manifest).relative_to(ROOT).as_posix()
    return _CACHE[tag]


def chunks(bound, world, *, buttons=0, new_level=0, frame_pending=0, torn=None, poke=None):
    """The PEEK chunks the reader would receive for one model state.

    `poke` overwrites single symbols after encoding, to build the malformed
    observations the decoder must refuse.
    """
    memory = bytearray(wram_image(world, buttons, new_level, frame_pending,
                                  world.player.camera, torn=torn))
    for symbol, value in (poke or {}).items():
        memory[bound.symbols[symbol] - abi.GB_WRAM_START] = value
    return [(offset, bytes(memory[offset:offset + count])) for offset, count in bound.ranges]


def states():
    """Named reachable states covering the fields the reconstruction needs."""
    title = reachable(())
    walking = reachable(((129, 1), (33, 30)))
    airborne = reachable(((129, 1), (33, 100), (49, 6)))
    landed = reachable(((129, 1), (33, 100), (49, 1), (33, 40)))
    scrolled = reachable(((129, 1), (33, 100), (49, 1), (33, 120)))
    fallen = reachable(((129, 1), (33, 150)))
    return [('title', title), ('walking', walking), ('airborne', airborne),
            ('landed', landed), ('scrolled', scrolled), ('retry', fallen)]


def clamped_states():
    """Reachable pairs whose camera clamp hides a tear, and one that does not.

    The camera is `clamp(x/16 - 72, 0, 608)`, so near the start and at the far
    right it does not move with the player and a partly written record passes
    the camera check unseen. The boundary, not this check, is the protection.
    """
    near_start = reachable(((129, 1), (33, 10)))
    moving = reachable(((129, 1), (33, 100)))
    return {'clamped': near_start, 'moving': moving}


def enemy_phases(step=12, count=19):
    """The same player position with the enemy at a different patrol phase."""
    result = []
    for k in range(0, step * count, step):
        world = reachable(((129, 1), (0, k), (33, 100), (49, 1), (33, 40)))
        if world.mode == PLAYING and world.player.grounded:
            result.append((k, world))
    return result
