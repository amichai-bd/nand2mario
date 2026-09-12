"""Acquisition boundary, autonomous play and failure handling on the fake.

The fake endpoint serves state from the reference models over the real wire
codecs, so the reader, decoder, renderer and strategy are exercised without a
simulator or a board.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from n2m import generated_interfaces as abi  # noqa: E402
from n2m import springtrail_play as play_module  # noqa: E402
from n2m import springtrail_state as state  # noqa: E402
from n2m.host.client import Client, UncertainCompletion  # noqa: E402
from n2m.interface_codec import pack_pixels  # noqa: E402
import state_support as support  # noqa: E402
from state_fake import Endpoint  # noqa: E402

BUDGET = {'wall_seconds': 240, 'frames': 1500, 'actions': 1500}


class Harness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image, cls.binding = support.binding()

    def endpoint(self, **kwargs):
        endpoint = Endpoint(image=self.image, **kwargs)
        return endpoint, Client(endpoint)

    def loaded(self, **kwargs):
        """A fake with the image already loaded and the core paused."""
        endpoint, client = self.endpoint(**kwargs)
        client.load(self.image)
        return endpoint, client


class BoundaryTests(Harness):
    def test_observation_lands_on_a_complete_update(self):
        endpoint, client = self.loaded()
        observation, provenance = play_module.observe(client, self.binding)
        self.assertTrue(play_module.BOUNDARY_FIRST <= provenance['ly'] <= play_module.BOUNDARY_LAST)
        self.assertEqual(observation['frame_pending'], 0)
        self.assertEqual(provenance['boundary'], 'vblank-complete')
        self.assertEqual(provenance['represents'], 'logical')
        self.assertEqual(provenance['display_lag_frames'], 1)
        self.assertEqual(provenance['rom_sha256'], support.ROM_SHA256)
        self.assertEqual(provenance['dot'], endpoint.game.dot)
        self.assertEqual(observation['mode_name'], 'TITLE')
        # Selected ranges only: the whole 8192-byte store is never downloaded.
        self.assertEqual(provenance['bytes'], self.binding.bytes)
        self.assertLess(provenance['bytes'], state.WRAM_BYTES // 16)
        self.assertTrue(all(count <= abi.WIRE_MAX_PAYLOAD for _offset, count in endpoint.peeks))

    def test_every_advance_is_a_whole_frame_and_keeps_the_phase(self):
        endpoint, client = self.loaded()
        first, before = play_module.observe(client, self.binding)
        client.write_host(abi.HOST_REG_INPUT, play_module.START)
        play_module._dots(client, play_module.PERIOD)
        second, after = play_module.observe(client, self.binding)
        self.assertEqual(after['ly'], before['ly'])
        self.assertEqual(after['dot'] - before['dot'], play_module.PERIOD)
        self.assertEqual(after['epoch'], before['epoch'])
        play_module._check_advance((first, before), (second, after), 1, play_module.START)

    def test_a_stuck_frame_flag_stops_the_reader_instead_of_guessing(self):
        _endpoint, client = self.loaded(defect='stuck-pending')
        with self.assertRaisesRegex(play_module.PlayFailure, 'STATE_BOUNDARY_UNREACHED'):
            play_module.observe(client, self.binding)

    def test_a_short_run_is_a_failure_not_a_silent_shortfall(self):
        _endpoint, client = self.loaded(defect='short-run')
        with self.assertRaisesRegex(play_module.PlayFailure, 'STATE_RUN_STOPPED'):
            play_module.observe(client, self.binding)

    def test_the_snapshot_at_the_boundary_is_one_frame_behind_the_state(self):
        """The publication delay the provenance declares, proved on the wire."""
        endpoint, client = self.loaded()
        client.write_host(abi.HOST_REG_INPUT, play_module.START)
        history = []
        for _ in range(4):
            observation, provenance = play_module.observe(client, self.binding)
            metadata, packed = client.snapshot()
            history.append((observation, provenance, metadata, packed))
            play_module._dots(client, play_module.PERIOD)
        for index in range(1, len(history)):
            previous = history[index - 1][0]
            _observation, _provenance, metadata, packed = history[index]
            self.assertEqual(metadata['size'], abi.FRAME_BYTES)
            # The completed source frame shows the state observed one boundary
            # earlier, never the state this observation just read.
            self.assertEqual(packed, pack_pixels(state.render(previous)))


class PlayTests(Harness):
    _baseline = None

    @classmethod
    def baseline(cls):
        """One full run from the title, shared by the tests that inspect it."""
        if cls._baseline is None:
            endpoint, client = Endpoint(image=cls.image), None
            client = Client(endpoint)
            kept = []
            result = play_module.play(client, cls.image, cls.binding, budget=BUDGET,
                                      retain=lambda step, observation, provenance: kept.append(step))
            cls._baseline = (endpoint, result, kept)
        return cls._baseline

    def test_reaches_won_from_the_title_within_the_declared_budget(self):
        endpoint, result, kept = self.baseline()
        self.assertEqual(result['status'], 'PASS', result.get('reason'))
        self.assertEqual(result['final']['mode'], 'WON')
        self.assertLessEqual(result['frames'], BUDGET['frames'])
        self.assertLessEqual(len(result['actions']), BUDGET['actions'])
        self.assertEqual(len(kept), len(result['actions']) + 1)
        self.assertEqual(result['attempts'], 1)
        # Every action is a complete eight-button mask chosen from observation.
        self.assertTrue(all(0 <= action['mask'] <= 255 for action in result['actions']))
        self.assertTrue(any(action['mask'] & play_module.A for action in result['actions']))
        # Ordinary completion: input released, core still paused, session certain.
        self.assertTrue(result['released'])
        self.assertFalse(result['uncertain'])
        self.assertEqual(endpoint.mask, 0)
        self.assertEqual(endpoint.state, abi.STATE_PAUSED)

    def test_no_game_memory_is_written_and_no_outcome_injected(self):
        endpoint, result, _kept = self.baseline()
        self.assertEqual(result['status'], 'PASS', result.get('reason'))
        self.assertEqual({address for address, _value in endpoint.writes},
                         {abi.HOST_REG_INPUT, abi.HOST_REG_INPUT_SOURCE})
        self.assertEqual(set(endpoint.requests) - {
            'PING', 'READ_HOST', 'WRITE_HOST', 'LOAD_BEGIN', 'LOAD_WRITE', 'LOAD_END',
            'READ_ROM', 'RESET', 'RUN_DOTS', 'PEEK'}, set())
        allowed = {(offset, count) for offset, count in self.binding.ranges}
        self.assertEqual(set(endpoint.peeks) - allowed, set())

    def test_a_later_start_produces_a_different_run_that_still_wins(self):
        """Changed start timing: the same strategy, a different action trace."""
        _endpoint, baseline, _kept = self.baseline()
        _late_endpoint, late_client = self.endpoint(delay=37)
        late = play_module.play(late_client, self.image, self.binding, budget=BUDGET)
        self.assertEqual(baseline['status'], 'PASS', baseline.get('reason'))
        self.assertEqual(late['status'], 'PASS', late.get('reason'))
        self.assertEqual(late['final']['mode'], 'WON')
        first = [action['mask'] for action in baseline['actions']]
        second = [action['mask'] for action in late['actions']]
        differing = sum(1 for a, b in zip(first, second) if a != b)
        self.assertGreater(differing, 20)
        self.assertNotEqual(len(first), len(second))

    def test_the_same_position_with_a_different_enemy_phase_chooses_differently(self):
        """Changed observed state: the decision, not a fixed timeline, moves."""
        strategy = play_module.Strategy()
        chosen = {}
        for phase, world in support.enemy_phases():
            observation = state.decode(self.binding, support.chunks(self.binding, world))
            mask, frames, reason = strategy.choose(observation)
            chosen[phase] = (observation['player']['pixel_x'], observation['enemy']['pixel_x'], mask)
            self.assertEqual(frames, 1)
            self.assertIn('lookahead', reason)
        positions = {entry[0] for entry in chosen.values()}
        self.assertEqual(len(positions), 1, 'the player must stand in one place')
        self.assertGreater(len({entry[1] for entry in chosen.values()}), 4)
        self.assertGreater(len({entry[2] for entry in chosen.values()}), 1)


class FailureTests(Harness):
    def test_input_that_never_reaches_the_game_stops_without_progress(self):
        _endpoint, client = self.endpoint(defect='ignore-input')
        result = play_module.play(client, self.image, self.binding,
                                  budget=dict(BUDGET, frames=400, actions=400,
                                              no_progress_frames=120))
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['reason'], 'STATE_NO_PROGRESS')
        self.assertTrue(result['released'])

    def test_a_held_input_register_stops_without_progress(self):
        _endpoint, client = self.endpoint(defect='input-stuck')
        result = play_module.play(client, self.image, self.binding,
                                  budget=dict(BUDGET, frames=400, actions=400,
                                              no_progress_frames=120))
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn(result['reason'], ('STATE_NO_PROGRESS', 'STATE_INPUT'))

    def test_an_exhausted_budget_is_reported_not_extended(self):
        _endpoint, client = self.endpoint()
        result = play_module.play(client, self.image, self.binding,
                                  budget=dict(BUDGET, frames=25, actions=25))
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn(result['reason'], ('STATE_BUDGET_FRAMES', 'STATE_BUDGET_ACTIONS'))
        self.assertLessEqual(result['frames'], 25)
        self.assertTrue(result['released'])

    def test_an_uncertain_reply_stops_the_session_and_sends_nothing_more(self):
        endpoint, client = self.endpoint(defect='short-peek')
        result = play_module.play(client, self.image, self.binding, budget=BUDGET)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result['uncertain'])
        self.assertFalse(result['released'])
        sent = len(endpoint.requests)
        with self.assertRaises(UncertainCompletion):
            client.read_host(abi.HOST_REG_STATE)
        self.assertEqual(len(endpoint.requests), sent)

    def test_a_wrong_image_is_refused_before_any_play(self):
        endpoint, client = self.endpoint()
        with self.assertRaisesRegex(state.StateFailure, 'STATE_ROM_UNSUPPORTED'):
            state.Binding('f' * 64, self.binding.symbols)
        self.assertEqual(endpoint.requests, [])


if __name__ == '__main__':
    unittest.main()
