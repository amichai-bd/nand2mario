"""Original stable-register scene oracle; no DUT state or timing inputs.

This is the spatial reference for directed scenes, not a fetch-timing model.
Window row is supplied by an independently scheduled activation history.
The standard window geometry helper rejects special WX0/166 behavior until the
timing oracle supplies that independently established activation mapping.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Registers:
    lcdc: int = 0x93
    scx: int = 0
    scy: int = 0
    bgp: int = 0xE4
    obp0: int = 0xE4
    obp1: int = 0xE4
    wx: int = 7


def palette(raw, value):
    return (value >> (raw * 2)) & 3


def tile_color(vram, address, x, y):
    low, high = vram[address + y * 2:address + y * 2 + 2]
    shift = 7 - x
    return ((low >> shift) & 1) | (((high >> shift) & 1) << 1)


def background(vram, regs, x, y, window_row=None):
    if not regs.lcdc & 1:
        return 0
    if window_row is not None and not 7 <= regs.wx <= 165:
        raise ValueError('special window activation requires timing oracle')
    window = window_row is not None and regs.lcdc & 0x20 and x >= regs.wx - 7
    if window:
        px, py = x - (regs.wx - 7), window_row
        mapping = 0x1C00 if regs.lcdc & 0x40 else 0x1800
    else:
        px, py = (x + regs.scx) & 255, (y + regs.scy) & 255
        mapping = 0x1C00 if regs.lcdc & 8 else 0x1800
    index = vram[mapping + ((py // 8) & 31) * 32 + ((px // 8) & 31)]
    if regs.lcdc & 0x10:
        tile = index * 16
    else:
        tile = 0x1000 + (index if index < 128 else index - 256) * 16
    return tile_color(vram, tile, px & 7, py & 7)


def selected_objects(oam, y, height):
    selected = []
    for index in range(40):
        sy, sx, tile, attr = oam[index * 4:index * 4 + 4]
        if sy - 16 <= y < sy - 16 + height:
            selected.append((sx, index, sy, tile, attr))
            if len(selected) == 10:
                break
    return sorted(selected)


def shade(vram, oam, regs, x, y, window_row=None):
    if len(vram) != 8192 or len(oam) != 160 or not (0 <= x < 160 and 0 <= y < 144):
        raise ValueError('complete memory and visible coordinate required')
    if not regs.lcdc & 0x80:
        raise ValueError('LCD-off presentation does not fabricate source pixels')
    raw_bg = background(vram, regs, x, y, window_row)
    bg_shade = palette(raw_bg, regs.bgp)
    if not regs.lcdc & 2:
        return bg_shade
    height = 16 if regs.lcdc & 4 else 8
    for sx, _, sy, tile, attr in selected_objects(oam, y, height):
        ox = x - (sx - 8)
        if not 0 <= ox < 8:
            continue
        oy = y - (sy - 16)
        if attr & 0x20:
            ox = 7 - ox
        if attr & 0x40:
            oy = height - 1 - oy
        if height == 16:
            tile &= 0xFE
        raw_obj = tile_color(vram, tile * 16, ox, oy)
        if raw_obj == 0:
            continue
        # The winner is selected before its BG-priority bit is applied.
        if attr & 0x80 and raw_bg != 0:
            return bg_shade
        return palette(raw_obj, regs.obp1 if attr & 0x10 else regs.obp0)
    return bg_shade
