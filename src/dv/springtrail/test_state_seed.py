"""Literal current fixture serialization and ordinary seed-loop contract."""
import unittest
from dataclasses import replace
from entities_reference import World, Entity
from motion_reference import Player
import entities_cases
import state_seed as S


class StateSeedTests(unittest.TestCase):
    def test_literal_layout_and_compatibility(self):
        ranges=((0xc000,1),(0xc010,14),(0xc024,1),(0xc026,7),(0xc060,10),
                (0xc02e,1),(0xc06a,14),(0xc078,12),(0xc090,7),(0xc300,56))
        self.assertEqual(S.RANGES,ranges)
        addresses=[a+i for a,n in ranges for i in range(n)]
        self.assertEqual(S.ADDRESSES,addresses)
        self.assertEqual(len(addresses),123)
        self.assertEqual(len(set(addresses)),123)
        self.assertIs(entities_cases.state_bytes,S.state_bytes)
        self.assertIs(entities_cases.ADDRESSES,S.ADDRESSES)
        self.assertIs(entities_cases.RANGES,S.RANGES)

    def test_literal_signed_entities_and_reserved_bytes(self):
        w=World(player=Player(x=-17,y=-1),curl=Entity(-17,32767,2,9,-8),
                moving=Entity(-32768,16,1,8,16),falling=Entity(32,-1,3,7,-16),
                lives=3,pending=1,timer_sub=59,timer_low=0x99,timer_high=2,
                expiring=1,stage=2,patrol_frame=8,stomp=16,rider=2)
        data=S.state_bytes(w,0x90,1)
        by_address=dict(zip(S.ADDRESSES,data))
        self.assertEqual(bytes(by_address[a] for a in range(0xc010,0xc014)),bytes.fromhex('ef ff ff ff'))
        self.assertEqual(by_address[0xc019],0x90)
        self.assertEqual(by_address[0xc02e],1)
        self.assertEqual(data[-63:-56],bytes.fromhex('03 01 3b 99 02 01 02'))
        expected=(bytes.fromhex('ef ff ff 7f 02 09 f8')+bytes(9)
                  +bytes.fromhex('00 80 10 00 01 08 10')+bytes(9)
                  +bytes.fromhex('20 00 ff ff 03 07 f0')+bytes(9)
                  +bytes.fromhex('08 10 02')+bytes(5))
        self.assertEqual(data[-56:],expected)

    def test_seed_copy_literal_cpu_loop(self):
        lines=S.seed_copy()
        self.assertEqual(lines[:10],['LD HL,SeedValues','LD DE,$C000','LD B,1','Seed0:',
                         'LD A,[HL+]','LD [DE],A','INC DE','DEC B','JR NZ,Seed0','LD DE,$C010'])
        self.assertEqual(lines[-9:],['JR NZ,Seed8','LD DE,$C300','LD B,56','Seed9:',
                         'LD A,[HL+]','LD [DE],A','INC DE','DEC B','JR NZ,Seed9'])
        self.assertEqual(len(lines),81)
        lines.clear()
        self.assertEqual(len(S.seed_copy()),81)


if __name__=='__main__':unittest.main()
