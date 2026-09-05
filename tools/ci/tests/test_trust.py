"""Adversarial host fixtures; no API mutation, licensed tool or runner execution."""
from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from tools.ci import controller, model, storage, waiter
from tools.ci.github import GitHub

SHA = '1' * 40
START = '2026-09-05T10:00:00Z'
NOW = '2026-09-05T11:00:00Z'


def fixture():
    cfg = {'schema': 1, 'enabled': True, 'repository': 'owner/project', 'repository_id': 11,
           'controller_id': 22, 'workflow_id': 33, 'workflow_path': '.github/workflows/trusted-product.yml',
           'workflow_blob': '2' * 40, 'environment': 'trusted-product'}
    req = {'sha': SHA, 'run_id': 44, 'attempt': 2, 'profile': 'questa-baseline'}
    run = {'id': 44, 'run_attempt': 2, 'head_sha': SHA, 'head_branch': 'main', 'workflow_id': 33,
           'event': 'workflow_dispatch', 'status': 'in_progress', 'conclusion': None,
           'repository': {'id': 11}, 'head_repository': {'id': 11},
           'actor': {'id': 22}, 'triggering_actor': {'id': 22}, 'run_started_at': START}
    snap = {'repository': {'id': 11, 'full_name': 'owner/project'}, 'account': {'id': 22},
            'workflow': {'id': 33, 'path': cfg['workflow_path'], 'state': 'active'},
            'workflow_blob': '2' * 40, 'run': run, 'attempt': deepcopy(run),
            'jobs': [{'id': 55, 'name': 'Trusted product attestation (questa-baseline)',
                      'run_id': 44, 'run_attempt': 2, 'head_sha': SHA, 'status': 'in_progress',
                      'conclusion': None, 'started_at': START}],
            'branch': {'name': 'main', 'protected': True, 'commit': {'sha': SHA}},
            'ancestry': 'identical', 'environment': {'name': 'trusted-product',
                      'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True}},
            'branch_policies': [{'name': 'main', 'type': 'branch'}]}
    status = {'id': 100, 'context': model.context(req), 'creator': {'id': 22},
              'target_url': model.run_url(cfg, req), 'created_at': START, 'state': 'success',
              'description': 'attested sha256:' + 'a' * 64}
    return cfg, req, snap, status


class AdmissionTests(unittest.TestCase):
    def test_exact_admission_and_final_ancestor(self):
        cfg, req, snap, _ = fixture()
        self.assertEqual(model.admit(cfg, req, snap, initial=True)['job_id'], 55)
        snap['branch']['commit']['sha'] = '3' * 40
        snap['ancestry'] = 'ahead'
        model.admit(cfg, req, snap, initial=False)
        with self.assertRaises(ValueError): model.admit(cfg, req, snap, initial=True)
        snap['ancestry'] = 'diverged'
        with self.assertRaises(ValueError): model.admit(cfg, req, snap, initial=False)

    def test_wrong_closed_admission_fields(self):
        changes = [
            ('repository.id', 12), ('repository.full_name', 'attacker/project'), ('account.id', 23),
            ('workflow.id', 34), ('workflow.path', '.github/workflows/other.yml'),
            ('workflow.state', 'disabled_manually'), ('workflow_blob', '3' * 40),
            ('run.run_attempt', 3), ('run.head_sha', '3' * 40), ('run.head_branch', 'feature'),
            ('run.event', 'pull_request'), ('run.status', 'completed'), ('run.conclusion', 'cancelled'),
            ('run.actor.id', 23), ('run.triggering_actor.id', 23), ('run.repository.id', 12),
            ('run.head_repository.id', 12), ('attempt.run_attempt', 1), ('attempt.head_sha', '3' * 40),
            ('branch.protected', False), ('environment.name', 'github-pages'),
            ('environment.deployment_branch_policy.custom_branch_policies', False),
        ]
        for name, value in changes:
            with self.subTest(name=name):
                cfg, req, snap, _ = fixture(); item = snap
                parts = name.split('.')
                for part in parts[:-1]: item = item[part]
                item[parts[-1]] = value
                with self.assertRaises(ValueError): model.admit(cfg, req, snap, initial=True)
        for change in ('empty', 'duplicate', 'other-name', 'complete', 'wrong-attempt', 'tag-policy'):
            with self.subTest(change=change):
                cfg, req, snap, _ = fixture()
                if change == 'empty': snap['jobs'] = []
                elif change == 'duplicate': snap['jobs'] *= 2
                elif change == 'other-name': snap['jobs'][0]['name'] = 'arbitrary command'
                elif change == 'complete': snap['jobs'][0]['status'] = 'completed'
                elif change == 'wrong-attempt': snap['jobs'][0]['run_attempt'] = 3
                else: snap['branch_policies'][0]['type'] = 'tag'
                with self.assertRaises(ValueError): model.admit(cfg, req, snap, initial=True)

    def test_remote_commands_paths_profile_and_disabled(self):
        cfg, req, snap, _ = fixture()
        for key in ('command', 'path', 'checkout', 'tool'):
            with self.assertRaises(ValueError): model.request({**req, key: 'attacker'})
        for profile in ('hardware', '../questa-baseline', 'echo owned'):
            with self.assertRaises(ValueError): model.request({**req, 'profile': profile})
        cfg['enabled'] = False
        with self.assertRaises(ValueError): model.admit(cfg, req, snap, initial=True)


class StatusTests(unittest.TestCase):
    def test_latest_individual_status_not_combined_or_old_success(self):
        cfg, req, _, status = fixture()
        self.assertEqual(model.latest_status(cfg, req, [status], START, NOW), status)
        pending = {**status, 'id': 101, 'state': 'pending'}
        self.assertEqual(model.latest_status(cfg, req, [status, pending], START, NOW)['state'], 'pending')
        failure = {**pending, 'state': 'failure'}
        self.assertEqual(model.latest_status(cfg, req, [failure, status], START, NOW)['state'], 'failure')
        self.assertIsNone(model.latest_status(cfg, req, [{**status, 'context': 'other'}], START, NOW))

    def test_foreign_stale_ambiguous_and_wrong_bound_statuses(self):
        cfg, req, _, status = fixture()
        for updates in ({'creator': {'id': 23}}, {'target_url': 'https://github.com/elsewhere'},
                        {'created_at': '2026-09-04T10:00:00Z'}, {'created_at': '2026-09-06T10:00:00Z'},
                        {'description': 'PASS'}, {'state': 'neutral'}):
            with self.subTest(updates=updates):
                with self.assertRaises(ValueError): model.latest_status(cfg, req, [{**status, **updates}], START, NOW)
        with self.assertRaises(ValueError): model.latest_status(cfg, req, [status, status], START, NOW)
        with self.assertRaises(ValueError):
            model.latest_status(cfg, req, [status, {**status, 'id': 101, 'created_at': '2026-09-04T10:00:00Z'}], START, NOW)

    def test_pagination_retains_individual_statuses(self):
        api = GitHub('test-not-a-credential')
        with patch.object(api, 'call', side_effect=[[{'id': i} for i in range(100)], [{'id': 101}]]) as call:
            self.assertEqual(len(api.pages('/fixed')), 101)
            self.assertIn('page=2', call.call_args.args[0])

    def test_waiter_rechecks_superseding_pending_and_cancellation(self):
        cfg, req, snap, status = fixture()
        class Fake:
            def snapshot(self, *args, **kwargs): return deepcopy(snap)
            def statuses(self, *args): return [status]
        self.assertEqual(waiter.wait(cfg, req, Fake(), timeout=1)['status'], 'PASS')
        class Superseded(Fake):
            count = 0
            def statuses(self, *args):
                self.count += 1
                return [status] if self.count == 1 else [{**status, 'id': 101, 'state': 'pending'}]
        with self.assertRaisesRegex(ValueError, 'superseded'): waiter.wait(cfg, req, Superseded(), timeout=1)
        class Cancelled(Fake):
            count = 0
            def snapshot(self, *args, **kwargs):
                self.count += 1; result = deepcopy(snap)
                if self.count == 3: result['run']['conclusion'] = 'cancelled'
                return result
        with self.assertRaises(ValueError): waiter.wait(cfg, req, Cancelled(), timeout=1)
        class Missing(Fake):
            def statuses(self, *args): return []
        with self.assertRaisesRegex(ValueError, 'timed out'):
            waiter.wait(cfg, req, Missing(), timeout=1, clock=iter([0, 0, 2, 2]).__next__, sleep=lambda _: None)


class StorageTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[3] / 'workdir/.tmp'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def test_canonical_envelope_replay_and_incomplete_inventory(self):
        self.assertEqual(model.digest({'a': 1, 'b': 2}), model.digest({'b': 2, 'a': 1}))
        with self.assertRaises(ValueError): model.canonical({'bad': float('nan')})
        cfg, req, _, _ = fixture()
        storage.consume(self.root, cfg, req, 'one')
        with self.assertRaisesRegex(ValueError, 'consumed'): storage.consume(self.root, cfg, req, 'two')
        with self.assertRaises(ValueError): storage.beneath(self.root, '../escape')
        empty = self.root / 'empty'; empty.mkdir()
        with self.assertRaises(ValueError): storage.inventory(empty)
        storage.freeze(empty / 'envelope.json', {'status': 'FAIL'})
        with self.assertRaises(FileExistsError): storage.freeze(empty / 'envelope.json', {'status': 'PASS'})

    def test_machine_lock_serializes_separate_process_and_recovers(self):
        code = 'from tools.ci.storage import machine_lock\nwith machine_lock(991150): print("owned")'
        with storage.machine_lock(991150):
            child = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
            self.assertNotEqual(child.returncode, 0)
            self.assertIn('already running', child.stderr)
        child = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(child.returncode, 0, child.stderr)

    def test_shipped_entry_points_fail_before_api_or_licensed_calls(self):
        args = ['--sha', SHA, '--run-id', '1', '--attempt', '1', '--profile', 'questa-baseline']
        with patch('tools.ci.controller.GitHub', side_effect=AssertionError('API called')):
            self.assertEqual(controller.main(args), 1)
        with patch('tools.ci.waiter.GitHub', side_effect=AssertionError('API called')):
            self.assertEqual(waiter.main(), 1)
        with patch.dict(os.environ, {'GH_TOKEN': 'secret', 'GITHUB_TOKEN': 'other', 'SAFE_UNLISTED': 'x'}):
            self.assertNotIn('GH_TOKEN', controller.child_environment())
            self.assertNotIn('GITHUB_TOKEN', controller.child_environment())
            self.assertNotIn('SAFE_UNLISTED', controller.child_environment())


class ControllerTests(unittest.TestCase):
    setUp = StorageTests.setUp
    tearDown = StorageTests.tearDown
    def prepare_repo(self, name):
        cfg, req, snap, status = fixture()
        root = self.root / name
        root.mkdir()
        def command(*args):
            return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL,
                                           text=True).strip()
        command('init', '-b', 'main')
        command('config', 'user.email', 'fixture@example.invalid')
        command('config', 'user.name', 'Host fixture')
        workflow = root / cfg['workflow_path']; workflow.parent.mkdir(parents=True)
        workflow.write_text('fixed workflow fixture\n', encoding='utf-8')
        cfg['workflow_blob'] = command('hash-object', cfg['workflow_path'])
        (root / 'cfg').mkdir()
        (root / 'cfg/trusted-ci.json').write_text(json.dumps(cfg), encoding='utf-8')
        (root / '.gitignore').write_text('workdir/\n', encoding='utf-8')
        command('add', '.'); command('commit', '-m', 'Host fixture')
        req['sha'] = command('rev-parse', 'HEAD')
        snap['workflow_blob'] = cfg['workflow_blob']
        for item in (snap['run'], snap['attempt'], snap['jobs'][0]): item['head_sha'] = req['sha']
        snap['branch']['commit']['sha'] = req['sha']
        return root, cfg, req, snap

    def fake_api(self, snapshot, *, cancel=False, pending_crash=False):
        class API:
            posts = []
            calls = 0
            def snapshot(self, *args, **kwargs):
                self.calls += 1
                value = deepcopy(snapshot)
                if cancel and self.calls > 1: value['run']['status'] = 'completed'
                return value
            def statuses(self, *args): return []
            def post(self, cfg, req, state, description, context, url):
                if pending_crash: raise KeyboardInterrupt('simulated process interruption before pending')
                self.posts.append(state)
                return {'id': len(self.posts), 'state': state}
        return API()

    @staticmethod
    def good_runner(root, cfg, req, invocation, folder, tools, recheck):
        recheck()
        (folder / 'fake-raw-exit.log').write_text('host fake, no licensed invocation\n', encoding='utf-8')
        return [{'host_fixture': target} for target in model.PROFILES[req['profile']]]

    def test_enabled_control_path_with_real_git_sources(self):
        root, cfg, req, snap = self.prepare_repo('one')
        api = self.fake_api(snap)
        with patch('tools.ci.controller.machine_state', return_value=self.root / 'common-state'):
            result = controller.execute(root, cfg, req, api, {}, runner=self.good_runner)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(api.posts, ['pending', 'success'])
        envelope = json.loads(Path(result['envelope']).read_text())
        self.assertEqual(storage.file_hash(Path(result['envelope'])), result['sha256'])
        self.assertNotIn('', envelope['controller_sources'])
        self.assertEqual(len(envelope['runs']), 2)

    def test_interrupted_attempt_rejected_from_another_checkout(self):
        root, cfg, req, snap = self.prepare_repo('one')
        second = self.root / 'two'
        subprocess.run(['git', 'clone', str(root), str(second)], check=True, capture_output=True)
        with patch('tools.ci.controller.machine_state', return_value=self.root / 'common-state'):
            with self.assertRaises(KeyboardInterrupt):
                controller.execute(root, cfg, req, self.fake_api(snap, pending_crash=True), {}, runner=self.good_runner)
            api = self.fake_api(snap)
            with self.assertRaisesRegex(ValueError, 'consumed'):
                controller.execute(second, cfg, req, api, {}, runner=self.good_runner)
            self.assertEqual(api.posts, [])

    def test_cancellation_missing_tool_partial_profile_and_dirty_source(self):
        root, cfg, req, snap = self.prepare_repo('one')
        for scenario in ('cancel', 'missing-tool', 'partial'):
            with self.subTest(scenario=scenario):
                api = self.fake_api(snap, cancel=scenario == 'cancel')
                def broken(*args):
                    if scenario == 'missing-tool': raise FileNotFoundError('missing fixed tool')
                    return []
                with patch('tools.ci.controller.machine_state', return_value=self.root / scenario):
                    if scenario == 'cancel':
                        with self.assertRaises(ValueError):
                            controller.execute(root, cfg, req, api, {}, runner=self.good_runner)
                        self.assertNotIn('success', api.posts)
                    else:
                        result = controller.execute(root, cfg, req, api, {}, runner=broken)
                        self.assertEqual(result['status'], 'FAIL')
                        self.assertEqual(api.posts, ['pending', 'failure'])
        (root / 'cfg/trusted-ci.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'not clean'): controller.sources(root, cfg, req)

    def test_hidden_index_flags_cannot_authorize_changed_source(self):
        for flag in ('--assume-unchanged', '--skip-worktree'):
            with self.subTest(flag=flag):
                root, cfg, req, _ = self.prepare_repo(flag[2:])
                subprocess.run(['git', '-C', str(root), 'update-index', flag, '.gitignore'], check=True)
                (root / '.gitignore').write_text('workdir/\nchanged\n', encoding='utf-8')
                self.assertEqual(controller.git(root, 'status', '--porcelain'), '')
                with self.assertRaisesRegex(ValueError, 'hidden index flags'):
                    controller.sources(root, cfg, req)


if __name__ == '__main__': unittest.main()
