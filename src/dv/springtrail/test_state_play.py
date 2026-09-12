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

    def test_a_settling_advance_is_accounted_for_instead_of_aborting(self):
        """Reaching the window may cost dots; that is reported, not a drift."""
        endpoint, client = self.loaded(defect='pending-once')
        first, before = play_module.observe(client, self.binding)
        self.assertEqual(before['advanced'] % play_module.LINE, 0)
        play_module._dots(client, play_module.PERIOD)
        second, after = play_module.observe(client, self.binding)
        self.assertEqual(after['advanced'], play_module.LINE)
        self.assertEqual(after['dot'] - before['dot'],
                         play_module.PERIOD + after['advanced'])
        self.assertNotEqual(after['ly'], before['ly'])
        # The phase moved, but by a declared amount, so this is not a drift.
        play_module._check_advance((first, before), (second, after), 1, 0)

    def test_a_whole_run_survives_repeated_settling_advances(self):
        _endpoint, client = self.endpoint(defect='pending-once')
        result = play_module.play(client, self.image, self.binding,
                                  budget=dict(BUDGET, frames=120, actions=120))
        self.assertIn(result['reason'], ('STATE_BUDGET_FRAMES', 'STATE_BUDGET_ACTIONS'))
        self.assertGreater(len(result['actions']), 100)

    def test_an_aligned_pair_matches_the_state_to_its_own_frame(self):
        endpoint, client = self.loaded()
        client.write_host(abi.HOST_REG_INPUT, play_module.START)
        for _ in range(3):
            play_module._dots(client, play_module.PERIOD)
        pair, packed = play_module.aligned_pair(client, self.binding)
        self.assertEqual(pair['next_provenance']['dot'] - pair['provenance']['dot'],
                         play_module.PERIOD)
        self.assertEqual(packed, pack_pixels(state.render(pair['observation'])))

    def test_checkpoints_are_claimed_once_and_cover_the_comparison_states(self):
        seen = []
        checkpoints = play_module.Checkpoints()
        for _name, world in support.states():
            observation = state.decode(self.binding, support.chunks(self.binding, world))
            found = checkpoints.classify(observation)
            if found:
                seen.append(found)
        self.assertEqual(len(seen), len(set(seen)), 'each checkpoint is claimed once')
        self.assertTrue(set(seen) <= set(play_module.Checkpoints.NAMES))
        self.assertIn('title', seen)
        self.assertEqual(set(checkpoints.missing()) & set(seen), set())

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
            'READ_ROM', 'RESET', 'RUN_DOTS', 'PEEK', 'HALT'}, set())
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

    def test_stationary_jump_escapes_changed_entity_phase(self):
        # Same source-model reachable history that exhausted all old candidates.
        world = dict(support.enemy_phases())[36]
        strategy = play_module.Strategy()
        observed = state.decode(self.binding, support.chunks(self.binding, world))
        base = strategy.power.update(state.to_world(observed), 0)
        self.assertEqual((base.player.x // 16, base.enemy_x, base.moving.x),
                         (235, 3944, 3024))
        self.assertTrue(all(strategy._rollout(base, *action) == strategy.DEAD
                            for action in strategy.ACTIONS[:-1]))
        self.assertEqual(strategy._rollout(base, 0, True), 259)
        mask, frames, reason = strategy.choose(observed)
        self.assertEqual((mask, frames), (16, 1))
        self.assertIn('lookahead', reason)

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



class ProgressionBoundaryTests(Harness):
    def test_staged_terminal_states_use_real_peeks_and_next_frame_publication(self):
        from dataclasses import replace
        from progress_reference import enter_stage as prior_enter_stage, TIMEUP, OVER, WON
        from entities_reference import World, initialize, update
        def enter_stage(w, b):
            return initialize(prior_enter_stage(w, b))
        for stage in range(3):
            for mode in (TIMEUP, OVER, WON):
                start = replace(enter_stage(World(stage=stage), 0), mode=mode, timer=17)
                endpoint, client = self.loaded(start=start)
                before, provenance = play_module.observe(client, self.binding)
                self.assertEqual(before['progress']['stage'], stage)
                self.assertEqual(before['mode'], mode)
                self.assertEqual(state.to_world(before), start)
                self.assertTrue(endpoint.peeks)
                client.write_host(abi.HOST_REG_INPUT, play_module.START)
                # The first frame samples Start; the following update consumes it.
                play_module._dots(client, play_module.PERIOD)
                play_module._dots(client, play_module.PERIOD)
                after, after_provenance = play_module.observe(client, self.binding)
                play_module._check_advance((before, provenance), (after, after_provenance),
                                           2, play_module.START)
                expected = update(start, play_module.START)
                self.assertEqual(state.to_world(after), expected)
                client.write_host(abi.HOST_REG_INPUT, 0)
                play_module._dots(client, play_module.PERIOD)
                play_module.observe(client, self.binding)
                self.assertEqual(endpoint.game.pixels(), state.render(after))


class RehearsalSafetyTests(Harness):
    def test_declared_37_frame_delay_is_neutral_traced_and_still_wins(self):
        endpoint, client = self.endpoint()
        result = play_module.play(client, self.image, self.binding, budget=BUDGET,
                                  start_delay_frames=37)
        self.assertEqual(result['status'], 'PASS', result.get('reason'))
        delay = result['actions'][:37]
        self.assertEqual(len(delay), 37)
        self.assertTrue(all((a['mask'], a['frames'], a['reason'], a['mode']) ==
                            (0, 1, 'start-delay', 'TITLE') for a in delay))
        self.assertEqual(delay[-1]['dot'] - delay[0]['dot'], 36 * play_module.PERIOD)
        self.assertTrue(result['actions'][37]['mask'] & play_module.START)
        self.assertLess(endpoint.requests.index('WRITE_HOST'), endpoint.requests.index('RESET'))
        self.assertEqual({a for a, _ in endpoint.writes},
                         {abi.HOST_REG_INPUT, abi.HOST_REG_INPUT_SOURCE})
        self.assertTrue(result['cleanup']['verified'])
        self.assertEqual(result['cleanup']['state'], abi.STATE_PAUSED)

    def test_invalid_delay_refuses_before_traffic_and_budget_includes_delay(self):
        for delay in (-1, True, 3):
            endpoint, client = self.endpoint()
            with self.assertRaisesRegex(play_module.PlayFailure, 'STATE_START_DELAY'):
                play_module.play(client, self.image, self.binding,
                                 budget=dict(BUDGET, frames=2, actions=2), start_delay_frames=delay)
            self.assertEqual(endpoint.requests, [])
        endpoint, client = self.endpoint()
        result = play_module.play(client, self.image, self.binding,
                                  budget=dict(BUDGET, frames=2, actions=2), start_delay_frames=2)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['reason'], 'STATE_BUDGET_ACTIONS')
        self.assertEqual(result['frames'], 2)
        self.assertEqual([a['reason'] for a in result['actions']], ['start-delay'] * 2)
        self.assertTrue(result['cleanup']['verified'])

    def test_failed_exit_never_keeps_pass_or_sends_after_uncertainty(self):
        from n2m.interface_codec import decode_packet, encode_packet
        for fault in ('reject', 'effective', 'state', 'timeout'):
            class ExitEndpoint(Endpoint):
                def write(self, packet):
                    header, _ = decode_packet(packet)
                    if fault == 'reject' and header['command'] == abi.COMMAND_HALT:
                        self.requests.append('HALT')
                        self.pending.extend(encode_packet(header['seq'], header['command'], b'',
                            kind=abi.WIRE_RESPONSE, status=abi.STATUS_STEP_LIMIT))
                        return len(packet)
                    return super().write(packet)
                def _read_host(self, address):
                    if fault == 'effective' and address == abi.HOST_REG_INPUT_EFFECTIVE:
                        return 1
                    if fault == 'state' and address == abi.HOST_REG_STATE:
                        return abi.STATE_PAUSED ^ 1
                    return super()._read_host(address)
            endpoint = ExitEndpoint(defect='timeout' if fault == 'timeout' else None)
            client = Client(endpoint, clock=iter(range(100)).__next__) if fault == 'timeout' else Client(endpoint)
            result = {'status': 'PASS', 'reason': 'original finding'}
            play_module.finish(client, result)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(result['reason'], 'original finding')
            self.assertFalse(result['cleanup']['verified'])
            self.assertFalse(result['released'])
            if fault == 'timeout':
                self.assertTrue(client.uncertain)
                before = list(endpoint.requests)
                play_module.finish(client, result)
                self.assertEqual(endpoint.requests, before)

if __name__ == '__main__':
    unittest.main()
