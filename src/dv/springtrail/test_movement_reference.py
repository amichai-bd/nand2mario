import unittest
from movement_reference import Player,step,solid


class MovementRules(unittest.TestCase):
    def test_walk_run_opposing(self):
        self.assertEqual(step(Player(),1).x,400)
        self.assertEqual(step(Player(),33).x,416)
        self.assertEqual(step(Player(),35).x,384)
        self.assertEqual(step(Player(),2).x,368)

    def test_jump_arc_and_held_button(self):
        p=Player();heights=[]
        for _ in range(50):
            p=step(p,16);heights.append(p.y)
        self.assertEqual(heights[:4],[1712,1636,1564,1496])
        self.assertEqual(min(heights),952)
        self.assertEqual(p.y,1792)
        self.assertTrue(p.grounded)
        self.assertEqual(step(p,16).y,1792)
        self.assertEqual(step(step(p,0),16).y,1712)

    def test_landing_side_head(self):
        landing=step(Player(x=80*16,y=79*16,vy=32,grounded=False),0)
        self.assertEqual((landing.y,landing.vy,landing.grounded),(80*16,0,True))
        side=step(Player(x=71*16,y=88*16,grounded=False),33)
        self.assertEqual((side.x,side.vx),(72*16,0))
        head=step(Player(x=80*16,y=105*16,vy=-32,grounded=False),0)
        self.assertEqual((head.y,head.vy,head.grounded),(104*16,0,False))

    def test_gap_and_bounds(self):
        p=Player(x=184*16)
        for _ in range(30):p=step(p,0)
        self.assertTrue(p.fell)
        self.assertGreaterEqual(p.y,144*16)
        self.assertEqual((step(Player(x=0),34).x,step(Player(x=0),34).camera),(0,0))
        right=step(Player(x=760*16),33)
        self.assertEqual((right.x,right.vx,right.camera),(760*16,0,608))
        self.assertEqual(step(Player(x=72*16),33).camera,2)

    def test_literal_world(self):
        self.assertFalse(solid(22,16));self.assertTrue(solid(21,16))
        self.assertTrue(solid(35,10));self.assertFalse(solid(36,10))
        self.assertTrue(solid(84,11));self.assertFalse(solid(85,11))


if __name__=='__main__':unittest.main()
