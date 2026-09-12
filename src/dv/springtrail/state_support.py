"""Shared fixtures for the Springtrail state reader and player tests.

Every fixture state is produced by the reference model, so it is a state the
ROM can actually hold. Hand-written records are not used: the decoder checks
cross-field invariants such as the camera, and an unreachable record would
fail them for the wrong reason.
"""
import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from n2m import generated_interfaces as abi  # noqa: E402
from n2m import springtrail_state as state  # noqa: E402
from state_fake import reachable, wram_image  # noqa: E402
from power_reference import PLAYING, update as model_update  # noqa: E402

ROM_SHA256 = next(iter(state.SUPPORTED))
TAG = 'sptest'
_CACHE = {}


def package(tag=TAG):
    """Build the current Springtrail image once per process and return its manifest."""
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


def binding(tag=TAG):
    """(image, Binding) for the image the repository builds from current sources."""
    return state.bind_package(ROOT, package(tag))


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


def enemy_phases(step=12, count=19):
    """The same player position with the enemy at a different patrol phase."""
    result = []
    for k in range(0, step * count, step):
        world = reachable(((129, 1), (0, k), (33, 100), (49, 1), (33, 40)))
        if world.mode == PLAYING and world.player.grounded:
            result.append((k, world))
    return result
