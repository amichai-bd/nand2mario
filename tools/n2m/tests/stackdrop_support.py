"""Load the existing independent game oracle without global module collisions."""
import importlib
from pathlib import Path
import sys
from unittest.mock import patch

directory = str(Path(__file__).resolve().parents[3]/'src/dv/stackdrop')
saved = {name: sys.modules.get(name) for name in ('reference', 'cases', 'screen')}
try:
    for name in saved:
        sys.modules.pop(name, None)
    with patch.object(sys, 'path', [directory, *sys.path]):
        reference = importlib.import_module('reference')
        cases = importlib.import_module('cases')
        screen = importlib.import_module('screen')
finally:
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module

Game, reference_cells, decode = reference.Game, reference.cells, screen.decode


def image(game):
    with patch.dict(sys.modules, {'cases': cases, 'reference': reference}):
        return screen.image(game)
