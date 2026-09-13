"""Launcher menu, load-and-hand-over, failure text and exit against a fake endpoint.

No board and no window: the catalogue comes from the repository's own manifests
and every UART step is answered by `Fake`.
"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import generated_interfaces as abi
from n2m import launcher as gl
from n2m.host.client import UncertainCompletion

ROOT = Path(__file__).resolve().parents[3]
BUILD = 'ab' * 16
IMAGE = bytes(abi.PROFILE_ROM_BYTES)


class Fake:
    """The Client surface the launcher uses, recording every request in order."""

    def __init__(self, *, build=BUILD, source=abi.INPUT_SOURCE_UART, effective=0,
                 lcdc=0x80, fail_on=None, load_error=None):
        self.build, self.source, self.effective = build, source, effective
        self.state, self.valid = abi.STATE_PAUSED, 0
        self.lcdc = lcdc
        self.fail_on, self.load_error = fail_on, load_error
        self.uncertain = False
        self.sequence = 0
        self.events = []
        self.dot = 0

    def identify(self):
        self.events.append('identify')
        return {'abi': abi.WIRE_ABI, 'build_id': self.build}

    def read_host(self, address):
        self.events.append(('read', address))
        return {abi.HOST_REG_IMAGE_VALID: self.valid, abi.HOST_REG_INPUT_SOURCE: self.source,
                abi.HOST_REG_INPUT_EFFECTIVE: self.effective, abi.HOST_REG_STATE: self.state}[address]

    def read_lcd_status(self):
        self.events.append('lcd')
        return {'ly': 0, 'stat': 0, 'lcdc': self.lcdc, 'mode': 0}

    def load(self, image):
        self.events.append(('load', len(image)))
        if self.load_error is not None:
            raise self.load_error
        self.valid, self.state = 1, abi.STATE_PAUSED
        return {'verified_bytes': len(image), 'image': {'bytes': len(image)}}

    def control(self, action, value=None):
        self.events.append((action, value))
        self.sequence += 1
        if action == 'INPUT':
            if self.fail_on is not None and value == self.fail_on:
                raise RuntimeError('wire rejected INPUT')
            self.effective = value
            self.dot += 100
        if action == 'RUN':
            self.state = abi.STATE_RUNNING
        if action == 'RESET':
            self.state = abi.STATE_PAUSED
        return {'dot': self.dot}


def build_report(target, cache='HIT'):
    attempt = f'workdir/builds/{gl.BUILD_TAG}/sw/build/{target}/runs/0123456789ab'
    return {'status': 'PASS', 'cache': cache, 'attempt': '0123456789ab', 'rom': attempt + '/image.gb'}


def launcher(client, **kwargs):
    kwargs.setdefault('runner', lambda root, target: build_report(target))
    return gl.Launcher(client, ROOT, expected_build=BUILD, **kwargs)


class CatalogueTests(unittest.TestCase):
    """The menu is the manifests; nothing about a game is retyped in the source."""

    def setUp(self):
        self.games = gl.games(ROOT)
        self.pins = json.loads((ROOT / gl.PIN_FILE).read_text(encoding='utf-8'))['external_roms']['images']
        self.targets = json.loads((ROOT / gl.TARGET_FILE).read_text(encoding='utf-8'))['targets']

    def test_every_loadable_game_is_listed_once(self):
        keys = [game['key'] for game in self.games]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), set(gl.SOURCE_TARGETS) | set(self.pins))

    def test_ours_come_first_and_name_themselves_from_the_target_registry(self):
        self.assertEqual([game['key'] for game in self.games[:2]], list(gl.SOURCE_TARGETS))
        for game in self.games[:2]:
            self.assertEqual(game['origin'], 'built here')
            self.assertEqual(game['kind'], 'package')
            self.assertEqual(game['name'], self.targets[game['key']]['title'].title())
            # No licence is invented for our own games; the section heading says so.
            self.assertIsNone(game['license'])

    def test_third_party_author_and_licence_come_from_the_manifest(self):
        for game in self.games[2:]:
            pin = self.pins[game['key']]
            self.assertEqual(game['kind'], 'external')
            self.assertEqual(game['origin'], 'third party')
            self.assertEqual((game['name'], game['author'], game['license']),
                             (pin['name'], pin['author'], pin['license']))

    def test_known_blank_games_are_listed_last_marked_and_explained(self):
        blank = [game for game in self.games if not game['boots']]
        self.assertEqual([game['key'] for game in blank], ['wyrmhole', 'rex-run'])
        self.assertEqual(self.games[-2:], blank)
        for game in blank:
            self.assertIn('LCD', game['note'])
            self.assertEqual(game['link'], gl.LIBRARY)
        self.assertTrue((ROOT / gl.LIBRARY.split('#')[0]).is_file())

    def test_every_other_game_is_listed_as_booting(self):
        self.assertEqual([game['key'] for game in self.games if game['boots'] and game['kind'] == 'external'],
                         [key for key in self.pins if key not in gl.BLANK])


class SequenceTests(unittest.TestCase):
    """Selecting a game loads it, resets, runs, and reaches the pad's preconditions."""

    def external(self, client, key='libbet', **kwargs):
        with patch.object(gl, 'read_external', return_value=(IMAGE, {'pin': key})) as reader:
            game = next(item for item in gl.games(ROOT) if item['key'] == key)
            started = launcher(client, **kwargs).start(game)
        return started, reader

    def test_external_selection_loads_resets_runs_then_hands_over(self):
        client = Fake()
        started, reader = self.external(client)
        self.assertEqual(reader.call_args.args[1], 'libbet')
        self.assertEqual([event for event in client.events if not isinstance(event, tuple) or event[0] != 'read'],
                         ['identify', ('load', abi.PROFILE_ROM_BYTES), ('RESET', None),
                          ('RUN', None), 'identify'])
        self.assertEqual(started['provenance'], {'external': {'pin': 'libbet'}})
        self.assertEqual(client.state, abi.STATE_RUNNING)

    def test_hand_over_uses_the_pads_own_preconditions(self):
        client = Fake()
        self.external(client)
        after = client.events[client.events.index('identify', 1):]
        self.assertEqual(after, ['identify', ('read', abi.HOST_REG_IMAGE_VALID),
                                 ('read', abi.HOST_REG_INPUT_SOURCE),
                                 ('read', abi.HOST_REG_INPUT_EFFECTIVE),
                                 ('read', abi.HOST_REG_STATE)])

    def test_progress_is_reported_while_the_load_is_in_flight(self):
        client, said = Fake(), []
        self.external(client, progress=said.append)
        self.assertTrue(any('Fetching' in line for line in said), said)
        self.assertTrue(any(str(abi.PROFILE_ROM_BYTES) in line for line in said), said)
        self.assertTrue(any('Resetting' in line for line in said), said)

    def test_a_source_built_game_reuses_its_current_attempt(self):
        client, calls = Fake(), []

        def runner(root, target):
            calls.append((root, target))
            return build_report(target)

        with patch.object(gl, 'read_package', return_value=(IMAGE, {'rom_sha256': 'x'})) as reader:
            started = launcher(client, runner=runner).start(gl.games(ROOT)[0])
        self.assertEqual(calls, [(ROOT, 'stackdrop')])
        self.assertEqual(started['provenance']['cache'], 'HIT')
        manifest = reader.call_args.args[1]
        self.assertEqual(manifest.name, 'result.json')
        self.assertEqual(manifest.parent.name, '0123456789ab')
        self.assertEqual(manifest.parent.parent.name, 'runs')

    def test_the_build_command_never_forces_a_rebuild(self):
        class Finished:
            stdout = json.dumps(build_report('stackdrop'))
        with patch.object(gl.subprocess, 'run', return_value=Finished()) as run:
            gl.run_build(ROOT, 'stackdrop')
        command = run.call_args.args[0]
        self.assertEqual(command[1:], [str(ROOT / 'tools/build.py'), 'sw', 'build', 'stackdrop',
                                       '--tag', gl.BUILD_TAG, '--json'])
        self.assertNotIn('--rebuild', command)

    def test_choosing_another_game_replaces_the_loaded_image(self):
        client = Fake()
        started, _ = self.external(client)
        self.assertEqual(started['game'], 'libbet')
        again, _ = self.external(client, key='airaki')
        self.assertEqual(again['game'], 'airaki')
        self.assertEqual([event for event in client.events if event == ('load', abi.PROFILE_ROM_BYTES)],
                         [('load', abi.PROFILE_ROM_BYTES)] * 2)


class FailureTests(unittest.TestCase):
    """Every failure a player can meet says what happened and what to do."""

    def game(self, key='libbet'):
        return next(item for item in gl.games(ROOT) if item['key'] == key)

    def start(self, client, error, key='libbet'):
        with patch.object(gl, 'read_external', side_effect=error):
            with self.assertRaises(gl.LauncherError) as raised:
                launcher(client).start(self.game(key))
        return str(raised.exception)

    def test_a_digest_mismatch_names_the_pin_and_the_cache(self):
        client = Fake()
        message = self.start(client, ValueError('external image hash mismatch: libbet'))
        self.assertIn('does not match its pinned digest', message)
        self.assertIn('workdir/private/external-roms', message)
        self.assertNotIn('Traceback', message)
        # A refused image never reaches the board; only the preconditions were read.
        self.assertEqual([event for event in client.events
                          if not isinstance(event, tuple) or event[0] != 'read'], ['identify'])

    def test_a_failed_load_names_the_link_and_leaves_nothing_loaded(self):
        client = Fake(load_error=ValueError('full ROM readback mismatch at offset 7'))
        instance = launcher(client)
        with patch.object(gl, 'read_external', return_value=(IMAGE, {'pin': 'libbet'})):
            with self.assertRaises(gl.LauncherError) as raised:
                instance.start(self.game())
        self.assertIn('read different bytes back', str(raised.exception))
        self.assertIn('UART wiring', str(raised.exception))
        self.assertIsNone(instance.loaded)

    def test_a_failed_build_names_the_command_that_shows_why(self):
        client = Fake()
        instance = launcher(client, runner=lambda root, target: {'status': 'FAIL', 'error': 'link error'})
        with self.assertRaises(gl.LauncherError) as raised:
            instance.start(self.game('stackdrop'))
        self.assertIn('sw build stackdrop', str(raised.exception))
        self.assertEqual([event for event in client.events
                          if not isinstance(event, tuple) or event[0] != 'read'], ['identify'])

    def test_a_held_board_reuses_the_pads_own_explanation(self):
        error = RuntimeError('trusted controller already running')
        self.assertEqual(gl.explain(self.game(), error), gl.explain_conflict(error))
        self.assertIn('holds this machine', gl.explain(self.game(), error))

    def test_an_uncertain_link_says_the_session_cannot_continue(self):
        message = self.start(Fake(), UncertainCompletion('LOAD_END: uncertain completion (timeout)'))
        self.assertIn('cannot send', message)

    def test_an_unfetchable_image_says_how_to_get_it_cached(self):
        message = self.start(Fake(), OSError('<urlopen error [Errno 11001] getaddrinfo failed>'))
        self.assertIn('could not be fetched', message)
        self.assertIn('network', message)

    def test_a_held_button_refuses_the_load_before_it_replaces_the_running_game(self):
        """The precondition is checked before the load, so nothing is destroyed."""
        client = Fake(effective=abi.BUTTON_LEFT)
        instance = launcher(client)
        with patch.object(gl, 'read_external', return_value=(IMAGE, {'pin': 'libbet'})) as reader:
            with self.assertRaises(gl.LauncherError) as raised:
                instance.start(self.game())
        self.assertIn('still has a button held', str(raised.exception))
        reader.assert_not_called()
        self.assertNotIn(('load', abi.PROFILE_ROM_BYTES), client.events)

    def test_an_unknown_failure_still_reads_as_a_sentence(self):
        message = self.start(Fake(), ValueError('something else'))
        self.assertTrue(message.startswith('Libbet'), message)
        self.assertIn('something else', message)


class BootWatchTests(unittest.TestCase):
    """A game that boots to nothing says so, rather than leaving a blank monitor."""

    def watch(self, key, times):
        clock = iter(times)
        return gl.BootWatch(next(item for item in gl.games(ROOT) if item['key'] == key),
                            grace=4.0, clock=lambda: next(clock))

    def test_a_drawing_game_is_never_reported_blank(self):
        watch = self.watch('libbet', [0.0, 1.0, 99.0])
        self.assertIsNone(watch.update(0x91))
        self.assertTrue(watch.done)
        self.assertIsNone(watch.update(0x00))

    def test_a_known_blank_game_names_its_cause_and_where_it_is_explained(self):
        watch = self.watch('wyrmhole', [0.0, 1.0, 9.0])
        self.assertIsNone(watch.update(0x00))
        text = watch.update(0x00)
        self.assertIn('has not enabled the LCD', text)
        self.assertIn('boot ROM', text)
        self.assertIn(gl.LIBRARY, text)
        self.assertIsNone(watch.update(0x00))

    def test_an_unexpected_blank_game_says_so_without_blaming_the_load(self):
        watch = self.watch('libbet', [0.0, 9.0])
        text = watch.update(0x00)
        self.assertIn('LCD is still off', text)
        self.assertNotIn(gl.LIBRARY, text)


class BackTests(unittest.TestCase):
    """Back releases before it leaves; the menu screen cannot clear a held mask."""

    def driver(self, client):
        from n2m.gui_pad import Controller, Driver
        return Driver(Controller(client))

    def test_back_releases_a_held_button_once_and_then_shows_the_menu(self):
        client = Fake()
        driver = self.driver(client)
        driver.button(0x25, True)
        self.assertEqual(driver.controller.held, [0x25])
        seen = []
        self.assertEqual(gl.leave_pad(driver, lambda: seen.append('menu') or 'menu',
                                      lambda text: seen.append(text)), 'menu')
        self.assertEqual(seen, ['menu'])
        self.assertEqual(driver.controller.held, [])
        self.assertEqual(client.effective, 0)
        self.assertEqual([event for event in client.events if event[0] == 'INPUT'],
                         [('INPUT', abi.BUTTON_LEFT), ('INPUT', 0)])
        self.assertFalse(client.uncertain)
        self.assertIsNone(driver.failure)

    def test_back_with_nothing_held_writes_nothing(self):
        client = Fake()
        driver = self.driver(client)
        self.assertEqual(gl.leave_pad(driver, lambda: 'menu', lambda text: text), 'menu')
        self.assertEqual(client.events, [])

    def test_a_failed_release_reports_it_instead_of_returning_to_the_menu(self):
        client = Fake(fail_on=0)
        driver = self.driver(client)
        driver.button(0x25, True)
        said = []
        gl.leave_pad(driver, lambda: said.append('menu'), lambda text: said.append(text))
        self.assertEqual(len(said), 1)
        self.assertNotEqual(said[0], 'menu')
        self.assertIn('UART write failed', said[0])
        self.assertIsNotNone(driver.failure)


class SessionTests(unittest.TestCase):
    """One session for menu, load and pad, and one release path out of it."""

    def window(self, *, play=None, choose='libbet'):
        def run(instance, controller, seconds=None):
            if choose:
                with patch.object(gl, 'read_external', return_value=(IMAGE, {'pin': choose})):
                    instance.start(instance.game(choose))
            for code, down in play or ():
                controller.apply(code, down)
        return run

    def loop(self, client, **kwargs):
        kwargs.setdefault('runner', lambda root, target: build_report(target))
        return gl.launcher_loop(client, ROOT, expected_build=BUILD, **kwargs)

    def test_exit_releases_input_verifies_zero_and_stays_certain(self):
        client = Fake()
        result = self.loop(client, window=self.window(play=[(0x27, True)]))
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(result['released'])
        self.assertEqual(result['cleanup'], {'verified': True, 'input_effective': 0, 'dot': client.dot})
        self.assertEqual(result['loaded'], 'libbet')
        self.assertFalse(client.uncertain)
        self.assertEqual(client.events[-2:], [('INPUT', 0), ('read', abi.HOST_REG_INPUT_EFFECTIVE)])

    def test_the_whole_session_identifies_once_before_any_load(self):
        client = Fake()
        self.loop(client, window=self.window())
        self.assertEqual(client.events[:3], ['identify', ('read', abi.HOST_REG_INPUT_SOURCE),
                                             ('read', abi.HOST_REG_INPUT_EFFECTIVE)])

    def test_a_menu_the_player_leaves_without_choosing_loads_nothing(self):
        client = Fake()
        result = self.loop(client, window=self.window(choose=None))
        self.assertEqual(result['status'], 'PASS')
        self.assertIsNone(result['loaded'])
        self.assertNotIn(('load', abi.PROFILE_ROM_BYTES), client.events)

    def test_a_refused_precondition_sends_no_control_traffic(self):
        for client in (Fake(build='cd' * 16), Fake(source=abi.INPUT_SOURCE_UART + 1), Fake(effective=1)):
            result = self.loop(client, window=self.window())
            self.assertEqual(result['status'], 'FAIL')
            self.assertFalse(result['released'])
            self.assertEqual(result['cleanup']['reason'], 'preconditions failed; no control sent')
            self.assertEqual([event for event in client.events
                              if not isinstance(event, tuple) or event[0] != 'read'], ['identify'])

    def test_an_uncertain_client_reports_that_rather_than_claiming_release(self):
        client = Fake()

        def window(instance, controller, seconds=None):
            controller.apply(0x27, True)
            client.uncertain = True
        result = self.loop(client, window=window)
        self.assertEqual(result['status'], 'FAIL')
        self.assertFalse(result['released'])
        self.assertEqual(result['cleanup'], {'verified': False, 'reason': 'uncertain; no further traffic'})

    def test_a_wire_failure_inside_the_window_still_releases(self):
        client = Fake(fail_on=abi.BUTTON_LEFT)

        def window(instance, controller, seconds=None):
            controller.apply(0x25, True)
        result = self.loop(client, window=window)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result['released'])
        self.assertEqual(result['cleanup']['input_effective'], 0)


if __name__ == '__main__':
    unittest.main()
