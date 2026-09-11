"""Host control-flow checks only; synthetic frames are not DUT evidence."""
import hashlib, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from n2m import generated_interfaces as abi
import board_bringup as bringup
from endurance import expected, LCD, PERIOD

ROM_SHA256 = hashlib.sha256(bytes(32768)).hexdigest()


def pack(image_bytes):
    return bytes(sum(image_bytes[n + i] << (2 * i) for i in range(4)) for n in range(0, 23040, 4))


class Endpoint:
    def __init__(self, *, wrong_build=False, wrong_pixels=False, halted_dot=0):
        self.dot = 0
        self.running = False
        self.mask = 0
        self.uncertain = False
        self.wrong_pixels = wrong_pixels
        self.build_id = 'wrong' if wrong_build else 'expected'
        self.halted_dot = halted_dot

    def identify(self):
        return dict(build_id=self.build_id, abi=1)

    def load(self, rom):
        assert len(rom) == 32768
        self.dot = 0
        return dict(verified_bytes=32768)

    def run_dots(self, count):
        return self.control('RUN_DOTS', count)

    def control(self, name, value=None):
        if name == 'RUN_DOTS':
            self.dot += value
            return dict(dot=self.dot, executed=value, reason=abi.WIRE_RUN_DOTS_COUNT)
        if name == 'HALT':
            self.running = False
            return dict(dot=self.dot)
        assert name == 'INPUT'
        self.mask = value
        return dict(dot=self.dot)

    def read_host(self, address):
        return {abi.HOST_REG_STATE: 0, abi.HOST_REG_DOT_LO: self.dot & 0xffffffff,
                abi.HOST_REG_DOT_HI: self.dot >> 32}[address]

    def snapshot(self):
        image_bytes, _ = expected('title')
        if self.wrong_pixels:
            image_bytes = bytes([b ^ 1 for b in image_bytes])
        return dict(epoch=2, seq=1, dot=self.dot, size=5760), pack(image_bytes)


def crc_proof_run(client):
    return {'status': 'crc-proof-double'}


class BoardBringupTests(unittest.TestCase):
    def test_complete_run_passes_and_leaves_board_idle(self):
        endpoint = Endpoint()
        with tempfile.TemporaryDirectory() as folder:
            result = bringup.run(endpoint, bytes(32768), ROM_SHA256, folder, lambda entry: None, 'expected', crc_proof_run)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['heartbeat']['dot'], bringup.TITLE_ADVANCE_DOT)
        self.assertEqual(result['crc_rejection'], {'status': 'crc-proof-double'})
        self.assertFalse(endpoint.running)
        self.assertEqual(endpoint.mask, 0)

    def test_build_id_mismatch_stops_before_load(self):
        endpoint = Endpoint(wrong_build=True)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(AssertionError, 'BRINGUP_BUILD_ID'):
                bringup.run(endpoint, bytes(32768), ROM_SHA256, folder, lambda entry: None, 'expected', crc_proof_run)

    def test_wrong_pixels_fail_and_still_clean_up(self):
        endpoint = Endpoint(wrong_pixels=True)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(AssertionError, 'ENDURANCE_PIXELS'):
                bringup.run(endpoint, bytes(32768), ROM_SHA256, folder, lambda entry: None, 'expected', crc_proof_run)
        self.assertFalse(endpoint.running)
        self.assertEqual(endpoint.mask, 0)


if __name__ == '__main__':
    unittest.main()
