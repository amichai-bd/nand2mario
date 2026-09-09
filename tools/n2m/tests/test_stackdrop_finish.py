"""The command must preserve uncertain completion and cleanup failures."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

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


class FinishTests(unittest.TestCase):
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
