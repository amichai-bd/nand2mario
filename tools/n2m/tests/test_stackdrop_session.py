"""Public-client stand-in checks sequencing and identity, not FPGA acceptance."""
import unittest

from stackdrop_support import Game, decode, image
from n2m import generated_interfaces as abi
from n2m.stackdrop_session import play, FRAME


class Board:
    def __init__(self):
        self.sequence = 10
        self.epoch = 4
        self.dots = 1000000
        self.running = False
        self.mask = 0
        self.game = Game()
        self.calls = []
        self.loaded = False
        self.stale = False

    def identify(self):
        return {'build_id': 'verified'}

    def read_host(self, address):
        return {abi.HOST_REG_DOT_HI: self.dots >> 32,
                abi.HOST_REG_DOT_LO: self.dots & 0xffffffff,
                abi.HOST_REG_STATE: abi.STATE_PAUSED if not self.running else abi.STATE_RUNNING,
                abi.HOST_REG_INPUT_SOURCE: abi.INPUT_SOURCE_UART,
                abi.HOST_REG_INPUT: self.mask,
                abi.HOST_REG_INPUT_EFFECTIVE: self.mask,
                abi.HOST_REG_IMAGE_VALID: 1}[address]

    def snapshot(self):
        pixels = image(self.game)
        packed = bytes(sum(pixels[i+j] << (2*j) for j in range(4))
                       for i in range(0, len(pixels), 4))
        dot = 999000 if not self.loaded else self.dots-1
        metadata = dict(epoch=self.epoch, seq=7 if not self.loaded else self.dots//FRAME,
                        dot=dot, size=abi.FRAME_BYTES)
        if self.stale and self.loaded:
            metadata['epoch'] -= 2
        return metadata, packed

    def load(self, image):
        self.calls.append(('LOAD', len(image)))
        self.epoch += 2
        self.dots = 0
        self.loaded = True
        self.game = Game()
        return {'verified_bytes': len(image)}

    def control(self, action, value=None):
        self.calls.append((action, value, self.dots))
        if action == 'RUN':
            self.running = True
        elif action == 'HALT':
            self.running = False
        elif action == 'INPUT':
            self.mask = value
        return {'dot': self.dots}

    def sleep(self, seconds):
        assert self.running
        for _ in range(3):
            self.game.update(self.mask)
            self.dots += FRAME


class SessionTests(unittest.TestCase):
    def prior(self):
        return dict(sequence=10, build_id='verified', halt_dot=1000000,
                    frame=dict(epoch=4, sequence=7, dot=999000))

    def test_baseline_complete_and_edge_windows(self):
        board = Board()
        events = []
        result = play(board, bytes(32768), self.prior(), 'baseline', decode,
                      lambda kind, value: events.append((kind, value)), sleep=board.sleep)
        self.assertLessEqual(result['drops'], 8)
        self.assertEqual(result['frame']['epoch'], 6)
        self.assertFalse(board.running)
        self.assertEqual(board.mask, 0)
        for kind, value in events:
            if kind == 'action':
                self.assertGreaterEqual(value['neutral']['end']-value['neutral']['begin'], 2*FRAME)
                self.assertGreaterEqual(value['pressed']['end']-value['pressed']['begin'], 3*FRAME)

    def test_reject_changed_identity_before_load(self):
        for field, value in (('sequence', 11), ('build_id', 'wrong'), ('halt_dot', 2)):
            board = Board()
            armed = []
            with self.assertRaises(ValueError):
                play(board, b'', dict(self.prior(), **{field:value}), 'baseline', decode,
                     lambda *args: None, sleep=board.sleep, ready=lambda: armed.append(True))
            self.assertFalse(board.loaded)
            self.assertEqual(armed, [])

    def test_reject_surviving_old_snapshot(self):
        board = Board()
        prior = self.prior()
        prior['frame']['epoch'] = 2
        with self.assertRaisesRegex(ValueError, 'OLD_FRAME_CHANGED'):
            play(board, b'', prior, 'baseline', decode, lambda *args: None, sleep=board.sleep)
        self.assertFalse(board.loaded)

    def test_reject_stale_new_epoch(self):
        board = Board()
        board.stale = True
        with self.assertRaisesRegex(Exception, 'FRAME_IDENTITY'):
            play(board, b'', self.prior(), 'baseline', decode, lambda *args: None, sleep=board.sleep)


if __name__ == '__main__':
    unittest.main()
