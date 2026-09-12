"""Host runner sensitivity; synthetic results are not physical evidence."""
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from n2m import generated_interfaces as abi
from interactions_reference import PLAYING, PAUSED, RETRY
from motion_frames import image
from endurance import (run, update, expected, check_pixels, terminal, exclusion, first_samples,
                       supervise, LCD, PERIOD, DOT_HZ, ROUTES, ROUTE_PERIODS, SPAWN, PLANS, CYCLE_SECONDS)

ZERO_ROM = bytes(32768)
ZERO_SHA = hashlib.sha256(ZERO_ROM).hexdigest()
PHASES = [(x, vx) for x in range(240*16, 296*16+1, 8) for vx in (-8, 8)]
SHORT = PLANS['short']


def packed(pixels):
    return bytes(sum(pixels[i+j] << (2*j) for j in range(4)) for i in range(0, 23040, 4))


def key(game):
    p = game.player
    return (game.mode, p.x, p.y, p.camera, game.collected, game.score, p.pose, p.facing, p.fell)


class Fake:
    def __init__(self, fault=None):
        self.wall = 0.; self.dot = 0; self.epoch = 6; self.mask = 0; self.running = False
        self.sequence = 177017; self.uncertain = False; self.fault = fault
        self.game = SPAWN; self.next_vb = 0; self.frames = {}; self.calls = []
        self.run_origin = 0; self.terminal_clock = 0

    def clock(self):
        if self.terminal_clock:
            self.terminal_clock -= 1
            if self.terminal_clock == 0:
                return self.wall-5
        return self.wall

    def tick(self, seconds):
        self.wall += seconds
        if self.running:
            self.advance(self.dot+round(seconds*DOT_HZ))

    def advance(self, target):
        if self.running and self.fault == 'dot-duration':
            target = min(target, self.run_origin+(SHORT*CYCLE_SECONDS-1)*DOT_HZ)
        while LCD+self.next_vb*PERIOD+65664 <= target:
            self.game = update(self.game, self.mask)
            self.frames[self.next_vb+2] = self.game
            self.next_vb += 1
        self.dot = target

    def call(self, name):
        self.calls.append(name); self.sequence += 1; self.tick(.001)

    def load(self, rom):
        self.call('load'); self.tick(1)
        if self.fault == 'lifecycle' and self.calls.count('load') == 4:
            raise RuntimeError('incomplete final load')
        self.dot = 0; self.epoch += 2; self.running = False; self.mask = 0
        self.game = SPAWN; self.next_vb = 0; self.frames = {}
        return {'verified_bytes': len(rom)}

    def read_host(self, addr):
        self.call('read')
        retired = (self.run_origin if self.running and self.fault == 'progress' else self.dot)//8
        return {abi.HOST_REG_DOT_LO: self.dot & 0xffffffff, abi.HOST_REG_DOT_HI: self.dot >> 32,
                abi.HOST_REG_RETIRE_LO: retired & 0xffffffff, abi.HOST_REG_RETIRE_HI: retired >> 32,
                abi.HOST_REG_STATE: int(self.running), abi.HOST_REG_IMAGE_VALID: 1,
                abi.HOST_REG_INPUT_SOURCE: 0, abi.HOST_REG_INPUT: self.mask,
                abi.HOST_REG_INPUT_EFFECTIVE: self.mask}[addr]

    def control(self, name, value=None):
        self.call(name)
        if name == 'HALT' and self.calls.count('load') == 4 and self.fault == 'cleanup':
            self.uncertain = True
            raise RuntimeError('final HALT reply lost')
        if name == 'RUN': self.running = True; self.run_origin = self.dot
        if name == 'HALT': self.running = False
        if name == 'RESET': self.epoch += 1; self.dot = 0
        if name == 'INPUT':
            self.mask = value
            if self.fault == 'input': return {'dot': self.dot+999999}
        return {'dot': self.dot}

    def run_dots(self, count):
        self.call('RUN_DOTS'); self.advance(self.dot+count)
        return dict(dot=self.dot, executed=count, reason=0)

    def snapshot(self):
        self.call('snapshot')
        if self.fault == 'stopped' and self.running: self.running = False
        seq = (self.dot-LCD-65664)//PERIOD
        game = self.frames.get(seq, SPAWN)
        data = packed(image(game))
        meta = dict(epoch=self.epoch, seq=seq, dot=LCD+seq*PERIOD+65663, size=5760)
        if self.fault == 'epoch': meta['epoch'] += 1
        if self.fault == 'pixel': data = data[:-1]+bytes([data[-1] ^ 64])
        if self.fault == 'stale': meta['dot'] -= 5*PERIOD; meta['seq'] -= 5
        if self.fault == 'uncertain': self.uncertain = True; raise RuntimeError('lost reply')
        self.tick(1.6)
        if self.fault == 'duration' and self.calls.count('snapshot') == 9:
            # The final valid sample is logged, then the elapsed-time source
            # reports a duration shorter than the frozen minimum.
            self.terminal_clock = 2
        return meta, data


def short(client, root, **extra):
    return run(client, ZERO_ROM, root, epoch=6, cycles=SHORT, rom_sha256=ZERO_SHA,
               clock=client.clock, sleep=client.tick, **extra)


class ModelTests(unittest.TestCase):
    def test_routes_converge_for_first_samples_and_enemy_phases(self):
        for route in ROUTES:
            with self.subTest(route=route):
                reference, _ = terminal(route)
                self.assertEqual(reference.mode, RETRY)
                self.assertTrue(reference.player.fell, 'RETRY must come from the gap, not enemy contact')
                for first in first_samples(route):
                    for phase in PHASES:
                        game, count = terminal(route, first, phase)
                        self.assertEqual(key(game), key(reference))
                        self.assertLess(count+8, ROUTE_PERIODS)
                # Settled: further held updates change nothing visible.
                held = reference
                for _ in range(300):
                    held = update(held, route)
                self.assertEqual(key(held), key(reference))
                # The player's world box never reaches the patrol minimum.
                self.assertLessEqual(reference.player.x+128, 240*16)

    def test_exclusion_covers_exactly_the_enemy_for_every_phase(self):
        for route in ROUTES:
            with self.subTest(route=route):
                wanted, indices = expected(f'retry-{route}')
                excluded = exclusion(terminal(route)[0])
                self.assertEqual(len(indices), 23040-len(excluded))
                touched = set()
                for phase in PHASES:
                    frame = image(terminal(route, enemy=phase)[0])
                    self.assertEqual(check_pixels(packed(frame), f'retry-{route}'), len(indices))
                    touched |= {i for i in excluded if frame[i] != wanted[i]}
                self.assertTrue(touched, 'exclusion must be non-vacuous')

    def test_spawn_samples_are_phase_independent_and_complete(self):
        for sample, mode in (('title', 0), ('play', PLAYING), ('paused', PAUSED)):
            for phase in PHASES[::20]:
                game = replace(SPAWN, mode=mode, enemy_x=phase[0], enemy_vx=phase[1])
                self.assertEqual(check_pixels(packed(image(game)), sample), 23040)

    def test_single_pixel_mutation_fails(self):
        for sample in ('title', 'play', 'paused', 'retry-33', 'retry-17'):
            data = bytearray(packed(expected(sample)[0]))
            data[-1] ^= 64
            with self.assertRaisesRegex(AssertionError, 'ENDURANCE_PIXELS'):
                check_pixels(data, sample)


class RunnerTests(unittest.TestCase):
    def test_complete_short_and_three_lifecycles(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Fake()
            result = short(client, Path(directory)/'run')
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual((len(result['lifecycles']), client.calls.count('load'), result['epoch']), (3, 4, 17))
            self.assertGreaterEqual(result['continuous_seconds'], SHORT*CYCLE_SECONDS)
            self.assertEqual([s['sample'] for s in result['samples']][:9],
                             ['title', 'play', 'retry-33', 'play', 'paused', 'play', 'retry-17', 'play', 'play'])
            self.assertFalse(client.running); self.assertEqual(client.mask, 0)
            start = client.calls.index('RUN'); end = client.calls.index('HALT', start)
            self.assertFalse(set(client.calls[start+1:end]) & {'RUN_DOTS', 'load', 'RESET'})

    def test_failures_never_pass(self):
        for fault in ('pixel', 'epoch', 'stale', 'input', 'uncertain', 'stopped', 'lifecycle', 'cleanup'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                client = Fake(fault)
                with self.assertRaises((AssertionError, RuntimeError)):
                    short(client, Path(directory)/'run')
                self.assertNotIn('"status": "PASS"', (Path(directory)/'run/result.json').read_text())
                if fault == 'uncertain': self.assertTrue(client.uncertain)

    def test_progress_duration_and_cap_guards(self):
        for fault, guard, extra in (('progress', 'ENDURANCE_PROGRESS', {}),
                                    ('duration', 'ENDURANCE_DURATION', {}),
                                    ('dot-duration', 'ENDURANCE_DOT_DURATION', {}),
                                    (None, 'ENDURANCE_WALL_CAP', {'deadline': 21})):
            with self.subTest(guard=guard), tempfile.TemporaryDirectory() as directory:
                client = Fake(fault); root = Path(directory)/'run'
                with self.assertRaisesRegex(AssertionError, guard):
                    short(client, root, **extra)
                result = json.loads((root/'result.json').read_text())
                self.assertEqual(result['status'], 'FAIL')
                self.assertIn(guard, result['error'])
                self.assertFalse(result['uncertain'])
                self.assertFalse(client.running); self.assertEqual(client.mask, 0)
                self.assertIn('final', result)

    def test_supervisor_kills_and_records_an_overrunning_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            sleeper = [sys.executable, '-c', 'import time; time.sleep(60)']
            self.assertEqual(supervise(sleeper, 13, out), 1)  # kill at cap-12 = 1 s
            budget = json.loads((out/'budget.json').read_text())
            self.assertEqual(budget['status'], 'TIMEOUT')
            self.assertTrue(budget['cleanup_complete'])
            self.assertLess(budget['elapsed_seconds'], 12)
            self.assertIn('raw_exit_code', budget)
            quick = [sys.executable, '-c', 'pass']
            self.assertEqual(supervise(quick, 13, out), 0)
            self.assertEqual(json.loads((out/'budget.json').read_text())['status'], 'FINISHED')

    @unittest.skipUnless(os.name == 'nt', 'Windows owned-tree cleanup')
    def test_supervisor_reaps_a_descendant_racing_the_cleanup(self):
        # The worker spawns a grandchild every 5 ms, so some land while cleanup
        # starts. taskkill /T walked a snapshot and left five alive per run with
        # cleanup_exit_code 0; the job reaps them all before cleanup_complete.
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); pids = out/'pids.txt'
            spawner = ("import subprocess,sys,time\nf=open(%r,'a')\nwhile True:\n"
                       "    f.write(str(subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']).pid)+chr(10))\n"
                       "    f.flush(); time.sleep(0.005)") % str(pids)
            self.assertEqual(supervise([sys.executable, '-u', '-c', spawner], 13, out), 1)
            budget = json.loads((out/'budget.json').read_text())
            self.assertEqual(budget['status'], 'TIMEOUT')
            spawned = [int(line) for line in pids.read_text().split()]
            self.assertGreater(len(spawned), 10, 'the worker must have been mid-spawn at expiry')
            import ctypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            alive = []
            for pid in spawned:
                handle = kernel.OpenProcess(0x100000, False, pid)
                if not handle:
                    continue  # gone or reused; nothing of ours to wait on
                try:
                    # Bounded wait proves the pid exited; 258 would be a live one.
                    if kernel.WaitForSingleObject(handle, 5000) != 0:
                        alive.append(pid)
                finally:
                    kernel.CloseHandle(handle)
            self.assertEqual(alive, [], f'{len(alive)} of {len(spawned)} descendants survived cleanup')
            self.assertTrue(budget['cleanup_complete'], budget.get('cleanup_error'))

    def test_wrong_rom_before_any_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Fake(); root = Path(directory)/'run'
            with self.assertRaisesRegex(AssertionError, 'ENDURANCE_ROM'):
                run(client, ZERO_ROM, root, epoch=6, cycles=SHORT, rom_sha256='0'*64)
            with self.assertRaisesRegex(AssertionError, 'ENDURANCE_ROM'):
                run(client, bytes(32767), root, epoch=6, cycles=SHORT, rom_sha256=ZERO_SHA)
            self.assertEqual(client.calls, [])
            self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
