"""The command must bind the current Stackdrop build and preserve uncertain
completion and cleanup failures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

# The command module loaded below imports ci and n2m, so tools/ goes on the path first.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
spec = importlib.util.spec_from_file_location('stackdrop_command', Path(__file__).resolve().parents[2]/'stackdrop_player.py')
command = importlib.util.module_from_spec(spec)
spec.loader.exec_module(command)


class Client:
    def __init__(self, uncertain=False, fail=False):
        self.uncertain, self.fail = uncertain, fail
        self.sequence = 5
        self.calls = []

    def control(self, *args):
        self.calls.append(args)
        if self.fail:
            self.uncertain = True
            raise RuntimeError('lost completion')
        self.sequence += 1


ROOT = Path(__file__).resolve().parents[3]
INPUTS = ('src/sw/stackdrop/main.asm', 'src/sw/stackdrop/layout.json')


def current_record(**overrides):
    inputs = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in INPUTS}
    return dict(dict(target='stackdrop', inputs=inputs), **overrides)


class PackageIdentityTests(unittest.TestCase):
    """The package must be a build of the checked-out source; no hash is pinned."""

    def check(self, record):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp)/'result.json'
            manifest.write_text(json.dumps(record))
            command.current_stackdrop(ROOT, manifest)

    def test_current_source_accepted(self):
        self.check(current_record())

    def test_other_target_and_stale_input_rejected(self):
        stale = dict(current_record()['inputs'], **{INPUTS[0]: '0'*64})
        for record in (current_record(target='springtrail'), current_record(inputs=stale)):
            with self.assertRaises(ValueError):
                self.check(record)

    def test_no_pinned_image_hash(self):
        source = (ROOT/'tools/stackdrop_player.py').read_text()
        self.assertIsNone(re.search(r'[0-9a-f]{64}', source))


class FinishTests(unittest.TestCase):
    def test_identity_failure_never_arms_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Client()
            command.finish(client, {'status':'FAIL'}, Path(tmp)/'result.json', armed=False)
            self.assertEqual(client.calls, [])

    def test_certain_and_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp:
            for uncertain in (False, True):
                client = Client(uncertain)
                path = Path(tmp)/'result.json'
                command.finish(client, {'status':'FAIL'}, path)
                self.assertEqual(client.calls, [] if uncertain else [('HALT',), ('INPUT',0)])
                self.assertEqual(json.loads(path.read_text())['uncertain'], uncertain)

    def test_cleanup_failure_retains_result_and_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Client(fail=True)
            path = Path(tmp)/'result.json'
            with self.assertRaises(RuntimeError):
                command.finish(client, {'status':'PASS'}, path)
            self.assertEqual(client.calls, [('HALT',)])
            self.assertEqual(json.loads(path.read_text())['status'], 'FAIL')
            self.assertTrue(json.loads(path.read_text())['uncertain'])
