"""Ordinary acquisition and exact fixed-block lookup source qualification."""
import unittest

import blocks_reference as blocks
from entities_reference import World, update
from frame_proofs import SCRIPT
from startup_anchor import Model, build
from state_seed import ADDRESSES, state_bytes

ROUTE = tuple((m,c) for m,c in SCRIPT)  # Only the already-qualified prefix is used.

def acquisition_masks():
    prefix = [m for m,c in ROUTE for _ in range(c)][:190]
    suffix = ((16,12),(0,40),(49,12),(33,13),(49,1),(33,108),(16,12),(0,20),(32,1))
    return prefix + [m for m,c in suffix for _ in range(c)]


def call(cpu, entry):
    cpu.pc, cpu.sp = entry, 0xdffc
    cpu.memory[0xdffc:0xdffe] = bytes((255,127))
    cycles = 0
    while cpu.pc != 0x7fff:
        cycles += cpu.step()
        assert cycles < 20000, 'SOURCE_ROUTINE_BOUND'
    return cycles * 4


class Acquisition(unittest.TestCase):
    def test_ordinary_route_matches_all_source_state_and_fires(self):
        rom,symbols = build()
        labels = {n:a for a,n in symbols.items()}
        cpu = Model(rom)
        while cpu.lcd is None:
            cpu.mcycles += cpu.step()
        w = World()
        for index,buttons in enumerate(acquisition_masks(),1):
            cpu.memory[0xc019] = buttons
            call(cpu,labels['UpdateGame'])
            w = update(w,buttons)
            self.assertEqual(bytes(cpu.memory[a] for a in ADDRESSES),state_bytes(w,buttons,0),index)
            if index == 198:
                self.assertEqual((w.power,w.blocks),(1,(1,0,0,0)))
            if index == 388:
                self.assertEqual((w.mode,w.power,w.coins,w.blocks),(1,2,1,(1,0,1,0)))
        self.assertEqual((w.mode,w.power,w.shot.ttl,w.throw),(1,2,63,8))

    def test_coin_reward_preserves_consumption_and_saturation(self):
        for power,coins,grant in ((0,0,None),(1,0,'power'),(2,0,None),(1,255,'power')):
            with self.subTest(power=power,coins=coins):
                result = blocks.resolve(blocks.reset(),coins,power,(64,11))
                self.assertEqual(result,((0,0,1,0),min(255,coins+1),128,512,80,grant))
        spent = blocks.resolve(blocks.reset(),0,0,(64,11))[0]
        self.assertEqual(blocks.resolve(spent,1,1,(64,11)),(spent,1,0,0,0,None))

    def test_fixed_lookup_full_byte_domain_and_source_bound(self):
        rom,symbols = build()
        labels = {n:a for a,n in symbols.items()}
        table = labels['BlockTable']
        self.assertEqual(rom[table:table+16],bytes((38,10,0,2,52,10,1,0,64,10,0,1,88,10,2,3)))
        cpu = Model(rom)
        maximum = 0
        for column in range(256):
            for row in range(256):
                cpu.b,cpu.c = column,row
                maximum = max(maximum,call(cpu,labels['FindBlockCell']))
                index = blocks.find(column,row)
                expected = (255,0xc0,4,10 if column in (88,89) else 88,table+16) if index is None else (index,0x70,index,10,table+4*index)
                self.assertEqual((cpu.a,cpu.f,cpu.d,cpu.e,cpu.hl),expected,(column,row))
                self.assertEqual((cpu.b,cpu.c),(column,row))
        self.assertEqual(maximum,208)
