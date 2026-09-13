"""Host fixture preparation and bounded source probes, never RTL acceptance."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time

from .records import atomic_json, file_hash


def run(root, build, name):
    """Use the real target and preparation entry points without tool discovery."""
    from . import catalogue, python_tb
    from .simulation import load_target
    started = time.monotonic()
    target, _ = load_target(root, name)
    if target.get('testbench') != 'python':
        raise ValueError(f'{name}: preflight requires a Python target')
    model, _ = catalogue.load(root)
    if model['units'].get(name, {}).get('kind') != 'sim':
        raise ValueError(f'{name}: missing simulation entry in src/dv/builder/catalogue.yaml')
    if target.get('preload') == 'mooneye-reg-f':
        raise ValueError(f'{name}: pinned external fixture tool preparation requires the existing Mooneye workflow')
    attempt = build/'preflight'/name
    attempt.mkdir(parents=True, exist_ok=False)
    before = {p: file_hash(root/p) for p in target['sources'] + target['python']['inputs']}
    try:
        python_tb.prepare(target, attempt, root)
        if target.get('preload'):
            if not (attempt/'fixture-preflight.json').is_file():
                raise ValueError('missing prepared fixture receipt; check python_tb.prepare dispatch')
            checks = json.loads((attempt/'fixture-preflight.json').read_text(encoding='utf-8'))
        else:
            checks = dict(preload='not applicable', banks='not applicable', scratch='not applicable')
        if any(file_hash(root/p) != digest for p,digest in before.items()):
            raise ValueError('declared input changed during preflight')
    except (ValueError, AssertionError, FileNotFoundError) as error:
        raise ValueError(f'{name}: fixture preflight: {error}') from error
    return dict(status='PASS', scope='host preparation only; no simulator or hardware',
                elapsed_seconds=time.monotonic()-started, inputs=before, checks=checks,
                artifacts={p.relative_to(root).as_posix(): file_hash(p)
                           for p in attempt.rglob('*') if p.is_file()})


def verify_prepared(root, target, attempt):
    """Also used by normal preparation before any compile/run command."""
    from .preload import verify
    name = target['preload']
    if not (attempt/'preload.json').is_file():
        raise ValueError(f'{name}: prepare dispatch produced no preload.json')
    record = verify(attempt)
    result = dict(preload=record['image_sha256'], banks='not applicable', scratch='not applicable')
    renderer = name in ('entities-render305', 'entities-render305-changed')
    oam = name.startswith('entities-oam305-')
    if renderer or oam:
        # Isolate imports to this checkout. Production callers are one-shot workers;
        # restoring sys.path also keeps in-process host callers well behaved.
        prior = sys.path[:]
        try:
            sys.path[:0] = [str(root/'tools'), str(root/'src/dv/springtrail')]
            anchor = importlib.import_module('startup_anchor')
            image = (attempt/'program.gb').read_bytes()
            metadata = 'entities-render.json' if renderer else 'entities_oam-unit.json'
            fixture = json.loads((attempt/metadata).read_text(encoding='utf-8'))
            from types import SimpleNamespace
            from sw.rom_build import build_target
            source = build_target(root, attempt/'source', SimpleNamespace(target='springtrail', rebuild=True), {})
            if source['status'] != 'PASS':
                raise ValueError(f"source image build failed: {source.get('error')}")
            game_path = root/source['rom']
            game = game_path.read_bytes()
            source_map = json.loads(game_path.with_name('map.json').read_text(encoding='utf-8'))
            result['shared_sections'] = shared_sections(image, game, fixture, source_map)
            if renderer:
                checker = importlib.import_module('entities_render_check')
                result['banks'] = upload_bank(anchor.Model, image, checker.expected_tiles())
            else:
                checker = importlib.import_module('entities_oam_check')
                short = name.endswith('-s')
                check = checker.Check(short, None if short else name[-1])
                result['scratch'] = scratch_writes(anchor.Model, image, check)
        finally:
            sys.path[:] = prior
    atomic_json(attempt/'fixture-preflight.json', result)
    return result


def shared_sections(image, game, fixture, source_map):
    if hashlib.sha256(image).hexdigest() != fixture.get('sha256'):
        raise ValueError('fixture ROM differs from its source build record')
    sections = fixture.get('sections', [])
    expected = fixture.get('shared_sections', {})
    wanted = {r['section']: (r['address'], r['size']) for r in source_map['sections']
              if r['section'] not in ('code', 'assets')}
    declared = {r['name']: (r['address'], r['size']) for r in sections}
    if not sections or len(declared) != len(sections) or declared != wanted or set(declared) != set(expected):
        raise ValueError('missing complete shared-section identity record')
    for row in sections:
        start, size, name = row['address'], row['size'], row['name']
        part = image[start:start+size]
        if not size or len(part) != size or part != game[start:start+size] or hashlib.sha256(part).hexdigest() != expected[name]:
            raise ValueError(f'shared source section differs: {name} at {start:04X}')
    return dict(count=len(sections), game_sha256=hashlib.sha256(game).hexdigest())


def upload_bank(model_type, image, expected):
    """Compare every ordinary source-executed VRAM upload, not raster placeholders."""
    writes = []
    class Probe(model_type):
        def write(self, address, value, cycle):
            if 0x8000 <= address < 0x9800:
                writes.append((address, value))
            super().write(address, value, cycle)
    model = Probe(image, lcdc_on=0x99)
    while model.lcd is None:
        if model.mcycles >= 100000:
            raise ValueError('upload probe did not reach LCD enable within 100000 M-cycles')
        model.mcycles += model.step()
    wanted = list(enumerate(expected, 0x8000))
    if writes != wanted:
        index = next((i for i,(a,b) in enumerate(zip(writes,wanted)) if a != b), min(len(writes),len(wanted)))
        raise ValueError(f'upload bank mismatch at byte {index}: source writes={len(writes)}, declared bytes={len(wanted)}')
    return dict(bytes=len(writes), sha256=hashlib.sha256(expected).hexdigest(), source_lcd=model.lcd)


def scratch_writes(model_type, image, check):
    """Reuse the selected OAM checker's existing state/write-range contract."""
    class Probe(model_type):
        def write(self, address, value, cycle):
            try:
                check.write(4*(self.mcycles+cycle), address, value)
            except AssertionError as error:
                raise ValueError(f'scratch/state contract rejected source write {address:04X}: {error}') from error
            super().write(address, value, cycle)
    model = Probe(image)
    while model.memory[model.pc] != 0x76:
        if model.mcycles >= 200000:
            raise ValueError('scratch probe did not reach HALT within 200000 M-cycles')
        model.mcycles += model.step()
    if not check.terminal or check.active is not None or len(check.reports) != len(check.selected):
        raise ValueError('scratch probe reached incomplete source terminal')
    return dict(cases=len(check.reports), source_dots=4*model.mcycles,
                scope='selected source writes; runtime retirement/hold/END still required')
