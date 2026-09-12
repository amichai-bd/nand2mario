"""Literal per-update entity boundaries, independent of assembled software."""
from dataclasses import replace
import unittest
from entities_reference import (World,Entity,initialize,update,spawn,_platforms,_curl,
                                MOVING_LO,CURL_X,FALL_X)
from motion_reference import Player
from power_reference import PLAYING,PAUSED,RETRY,LARGE,HURT,Shot
from movement_reference import solid


class Entities(unittest.TestCase):
    def game(self, **changes):
        return replace(World(mode=PLAYING,alive=False),**changes)

    def test_stage_init_and_swept_envelope(self):
        for stage in range(3):
            w=initialize(self.game(stage=stage))
            self.assertEqual((w.curl.x,w.moving.x,w.falling.x),
                             (CURL_X[stage]*16,MOVING_LO[stage]*16,FALL_X[stage]*16))
            for col in range(MOVING_LO[stage]//8,(MOVING_LO[stage]+55)//8+1):
                self.assertFalse(any(solid(col,row,stage) for row in range(12,15)))

    def test_moving_endpoints(self):
        for x,v,expected in ((207,16,(208,-16)),(208,-16,(207,-16)),(176,-16,(176,16))):
            moving,_=_platforms(self.game(moving=Entity(x*16,112*16,1,0,v)))
            self.assertEqual((moving.x,moving.vx),(expected[0]*16,expected[1]))

    def test_neutral_carry_and_jump(self):
        w=self.game(player=Player(x=184*16,y=96*16))
        got=update(w,0)
        self.assertEqual((got.player.x,got.player.y,got.player.grounded,got.player.jump,got.rider),
                         (185*16,96*16,True,0,1))
        got=update(w,16)
        self.assertEqual(got.player.x,184*16)
        self.assertLess(got.player.y,96*16)
        self.assertEqual(got.rider,0)

    def test_landing_and_right_edge(self):
        w=self.game(player=Player(x=184*16,y=95*16,jump=3,grounded=False))
        got=update(w,0)
        self.assertEqual((got.player.y,got.player.grounded,got.rider),(96*16,True,1))
        w=replace(w,player=replace(w.player,x=201*16)) # new platform right=201
        self.assertEqual(update(w,0).rider,0)

    def test_falling_delay_and_absence(self):
        w=self.game(player=Player(x=370*16,y=95*16,jump=3,grounded=False))
        got=update(w,0)
        self.assertEqual((got.falling.state,got.falling.timer,got.falling.y),(1,16,112*16))
        falling=_platforms(replace(w,falling=Entity(368*16,112*16,1,1)))[1]
        self.assertEqual((falling.state,falling.y,falling.timer),(2,114*16,0))
        falling=_platforms(replace(w,falling=Entity(368*16,142*16,2)))[1]
        self.assertEqual((falling.state,falling.y),(3,144*16))

    def test_curl_range_timer(self):
        e=Entity(328*16,120*16)
        self.assertEqual(_curl(e,Player(x=295*16)),e)
        self.assertEqual((_curl(e,Player(x=296*16)).state,_curl(e,Player(x=296*16)).timer),(1,32))
        self.assertEqual(_curl(replace(e,state=1,timer=1),Player()),replace(e,timer=32))
        self.assertEqual(_curl(replace(e,timer=1),Player(x=328*16)),e)

    def test_curl_contact_power_and_shot(self):
        w=self.game(player=Player(x=328*16,y=112*16),curl=Entity(328*16,120*16,1,20))
        self.assertEqual(update(w,0).mode,RETRY)
        got=update(replace(w,power=LARGE),0)
        self.assertEqual((got.mode,got.power,got.phase,got.phase_timer),(PLAYING,0,HURT,32))
        self.assertEqual(update(replace(w,invincible=10),0).curl.state,2)
        got=update(replace(w,phase=HURT,phase_timer=20,shot=Shot(327*16,120*16,16,0,20)),0)
        self.assertEqual(got.curl.state,1)
        self.assertGreater(got.shot.ttl,0)

    def test_patrol_stomp_and_pause(self):
        w=self.game(alive=True,enemy_x=256*16,player=Player(x=256*16,y=105*16,grounded=False,jump=3))
        full=update(replace(w,player=replace(w.player,y=101*16)),0)
        self.assertEqual((full.alive,full.stomp,full.player.index),(False,16,13))
        # Direct contact witness holds the collision position before motion.
        from entities_reference import power
        got=power.enemy_contact(w)
        self.assertEqual((got.alive,got.player.jump,got.player.index),(False,1,13))
        paused=replace(w,mode=PAUSED,stomp=16,curl=Entity(328*16,120*16,1,32))
        got=update(paused,0)
        self.assertEqual((got.moving,got.falling,got.curl,got.stomp),
                         (paused.moving,paused.falling,paused.curl,16))

    def test_offscreen_timer_trajectories(self):
        w=self.game(curl=Entity(328*16,120*16,1,32),
                    falling=Entity(368*16,112*16,1,16))
        for _ in range(15):
            w=update(w,0)
        self.assertEqual((w.falling.state,w.falling.timer,w.falling.y),(1,1,112*16))
        w=update(w,0)
        self.assertEqual((w.falling.state,w.falling.y),(2,114*16))
        for _ in range(16):
            w=update(w,0)
        self.assertEqual((w.curl.state,w.curl.timer,w.falling.state,w.falling.y),
                         (0,32,3,144*16))
        for _ in range(32):
            w=update(w,0)
        self.assertEqual((w.curl.state,w.curl.timer,w.falling.state),(0,0,3))

    def test_simultaneous_patrol_precedes_curl(self):
        # Ordinary contact boxes seeded together to exercise deterministic order.
        w=self.game(alive=True,enemy_x=256*16,power=LARGE,
                    player=Player(x=256*16,y=112*16),curl=Entity(256*16,120*16,1,20))
        got=update(w,0)
        self.assertEqual((got.mode,got.power,got.phase,got.phase_timer,got.alive,got.curl.state),
                         (PLAYING,0,HURT,32,True,1))
        fatal=update(replace(w,power=0),0)
        self.assertEqual((fatal.mode,fatal.curl.state),(RETRY,1))

    def test_slot_exhaustion_and_reset(self):
        w=self.game()
        self.assertEqual(spawn(w,4),(w,False))
        self.assertEqual(spawn(w,1),(w,False))
        w=replace(w,mode=PAUSED,falling=replace(w.falling,state=3),curl=replace(w.curl,state=2))
        got=update(w,64)
        self.assertEqual((got.falling.state,got.curl.state,got.rider),(0,0,0))
        self.assertEqual(got.lives,2)


if __name__=='__main__':
    unittest.main()
