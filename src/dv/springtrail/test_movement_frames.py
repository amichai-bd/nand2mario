import unittest,zlib
from movement_frames import image
from movement_reference import Player,step


class OriginalMovementFrames(unittest.TestCase):
    def test_title_and_first_movement(self):
        self.assertEqual(zlib.crc32(image(title=True)),0x5324bc1f)
        first=step(Player(),129)
        self.assertEqual((first.x,first.y,first.camera),(400,1792,0))
        frame=image(first)
        self.assertEqual(len(frame),23040)
        self.assertEqual(zlib.crc32(frame),0xae96d493)
        self.assertEqual(frame[112*160+27:112*160+31],bytes((0,3,3,0)))

    def test_fixed_round_trip(self):
        player=Player()
        checkpoints={28:(80,8),148:(320,248),152:(328,256),156:(336,264),328:(680,608)}
        for update in range(1,370):
            player=step(player,33+(16 if update in (65,161,257) else 0))
            self.assertFalse(player.fell)
            if update in checkpoints:
                self.assertEqual((player.x//16,player.camera),checkpoints[update])
        self.assertEqual((player.x,player.vx,player.camera),(12160,0,608))
        for update in range(1,382):
            player=step(player,34+(16 if update in (73,169,265) else 0))
            self.assertFalse(player.fell)
        self.assertEqual((player.x,player.y,player.vx,player.camera),(0,1792,0,0))


if __name__=='__main__':unittest.main()
