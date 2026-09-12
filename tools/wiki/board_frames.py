#!/usr/bin/env python3
"""Board-captured frame archives for the wiki showcase loops.

`ingest` reads one retained capture session -- `play.py showcase`, which drives
the pinned Libbet image, or `frame_proofs.py full --showcase`, which drives the
Springtrail image the repository builds -- and writes the committed archive
`tools/wiki/board_frames/<name>.json`. The archive holds the session's
provenance and, per sampled frame, its identity (sequence, completion dot,
applied JOYP mask, CRC32 of the packed board bytes) and the indexed-PNG payload
the SVG embeds. No packed frame and no decoded PNG file is committed; the
archive is the only copy of the pixels, and `tools/wiki/showcase.py` regenerates
each SVG from it byte for byte.

The archive also records the encoding measurement that chose the payload:
`bytes_indexed_png` against `bytes_path_runs`, the rect-run technique
`showcase.paths()` uses for the model-rendered loop, measured on this very
sequence.
"""
from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = Path(__file__).resolve().parent / 'board_frames'
# The four DMG shades, the palette wiki/showcase/*.svg already draws with.
SHADES = ('#ffffff', '#d0d0d0', '#686868', '#181818')
WIDTH, HEIGHT = 160, 144
PIXELS = WIDTH * HEIGHT


def unpack(packed):
    """160x144 shade indices from the 5760 packed bytes `host snapshot` returns."""
    assert len(packed) == 5760, 'FRAME_SIZE'
    return bytes((value >> shift) & 3 for value in packed for shift in (0, 2, 4, 6))


def indexed_png(pixels):
    """A 2-bit indexed PNG of one frame: four palette entries, four pixels a byte.

    Indexed 2bpp is the smallest lossless form of a DMG frame, and 160 pixels
    fill whole bytes, so no filter beyond None is worth its own byte.
    """
    assert len(pixels) == PIXELS, 'FRAME_PIXELS'
    rows = []
    for y in range(HEIGHT):
        row = bytearray(b'\x00')
        for x in range(0, WIDTH, 4):
            i = y * WIDTH + x
            row.append((pixels[i] << 6) | (pixels[i + 1] << 4) | (pixels[i + 2] << 2) | pixels[i + 3])
        rows.append(bytes(row))

    def chunk(kind, data):
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)

    palette = b''.join(bytes(int(shade[i:i + 2], 16) for i in (1, 3, 5)) for shade in SHADES)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', WIDTH, HEIGHT, 2, 3, 0, 0, 0))
            + chunk(b'PLTE', palette)
            + chunk(b'IDAT', zlib.compress(b''.join(rows), 9))
            + chunk(b'IEND', b''))


def data_uri(pixels):
    return 'data:image/png;base64,' + base64.b64encode(indexed_png(pixels)).decode('ascii')


def path_runs_bytes(pixels):
    """Size of the same frame under showcase.paths(), for the encoding comparison."""
    sys.path.insert(0, str(ROOT / 'tools'))
    from wiki.showcase import paths
    drawn = {(x, y): pixels[y * WIDTH + x] for y in range(HEIGHT) for x in range(WIDTH)
             if pixels[y * WIDTH + x]}
    return len(paths(drawn))


def load(name):
    """The committed archive for one loop."""
    return json.loads((ARCHIVES / f'{name}.json').read_text(encoding='utf-8'))


def libbet_session(folder):
    """Sampled frames from one `play.py showcase` session."""
    result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    assert result['status'] == 'PASS' and result['plan'] == 'showcase', 'SESSION_NOT_A_PASSING_SHOWCASE'
    applied = [(row['applied']['dot'], row['mask']) for row in result['inputs']]
    provenance = dict(
        program='Libbet and the Magic Floor v0.08', driver='src/dv/libbet/play.py',
        command='python src/dv/libbet/play.py showcase',
        licence='Zlib, Damian Yerrick; pinned in tools/n2m/dependencies.json',
        checked='frame identity, CRC32 and changed-pixel counts recorded per frame; '
                'no reference renderer exists for third-party code',
        wire_build_id=result['endpoint']['build_id'], wire_abi=result['endpoint'].get('abi'),
        wall_seconds=result['wall_seconds'], intro_seconds=result['args']['intro_seconds'],
        hold_frames=result['args']['hold'],
        inputs=[dict(label=row['label'], mask=row['mask'], dot=row['applied']['dot'])
                for row in result['inputs']])
    mask, frames = 0, []
    for entry in result['frames']:
        packed = folder / (Path(entry['png']).stem + '.2bpp')
        data = packed.read_bytes()
        assert f'{zlib.crc32(data) & 0xffffffff:08x}' == entry['crc32'], 'SESSION_FRAME_CRC'
        # The mask in force when the frame completed: the last INPUT applied at
        # or before its completion dot, in the order the session applied them.
        for dot, value in applied:
            if dot <= entry['metadata']['dot']:
                mask = value
        frames.append(dict(label=entry['label'], index=entry['index'], seq=entry['metadata']['seq'],
                           dot=entry['metadata']['dot'], mask=mask, crc32=entry['crc32'],
                           changed=entry.get('pixels_changed_from_previous'),
                           pixels=unpack(data)))
    return provenance, frames


def springtrail_session(folder):
    """Sampled frames from one `frame_proofs.py full --showcase` session.

    The session folder is the launcher's `workdir/builds/<tag>/frames/full-<stamp>/`:
    `build.json` from the launcher, `session.json` from the worker and
    `run/result.json` with the packed frames from the driver. Every sample was
    compared against all 23040 pixels of the block-aware model before the
    driver retained it; the CRC32 here is the driver's, over the unpacked
    shade indices, the value FRAME_PROOFS.md records per capture.
    """
    session = json.loads((folder / 'session.json').read_text(encoding='utf-8'))
    result = json.loads((folder / 'run' / 'result.json').read_text(encoding='utf-8'))
    build = json.loads((folder / 'build.json').read_text(encoding='utf-8'))
    assert session['status'] == result['status'] == 'PASS' and result['showcase'],         'SESSION_NOT_A_PASSING_SHOWCASE'
    assert result['rom_sha256'] == build['sha256'], 'SESSION_IMAGE'
    provenance = dict(
        program='Springtrail', driver='src/dv/springtrail/frame_proofs.py',
        command='python src/dv/springtrail/frame_proofs.py full --showcase',
        checked='every sampled frame compared against all 23040 pixels of '
                'src/dv/springtrail/blocks_frames.image before it was retained',
        wire_build_id=session['endpoint']['build_id'], wire_abi=session['endpoint'].get('abi'),
        image_sha256=build['sha256'], anchor=build['package'].get('anchor'),
        epoch=result['epoch'], plan=result['plan'], checkpoints=result['checkpoints'],
        final_dot=result['final_dot'], wall_seconds=session['wall_seconds'],
        lcd=result['lcd'], period=result['period'],
        sampled_checkpoints=[k + 2 for k in result['showcase_checkpoints']],
        proof_captures=[dict(name=c['name'], game=c['game'], seq=c['metadata']['seq'],
                             dot=c['metadata']['dot'], crc32=c['crc32']) for c in result['captures']],
        inputs=[dict(mask=row['mask'], dot=row['dot'], vblank=row['vblank']) for row in result['inputs']])
    frames = []
    for entry in result['samples']:
        pixels = unpack((folder / 'run' / entry['file']).read_bytes())
        assert f'{zlib.crc32(pixels) & 0xffffffff:08x}' == entry['crc32'], 'SESSION_FRAME_CRC'
        assert entry['checked_pixels'] == PIXELS, 'SESSION_FRAME_UNCHECKED'
        frames.append(dict(label=entry['name'], game=entry['game'], seq=entry['metadata']['seq'],
                           dot=entry['metadata']['dot'], pause_dot=entry['pause_dot'],
                           mask=entry['mask'], crc32=entry['crc32'],
                           state=list(entry['anchor'][:8]), pixels=pixels))
    return provenance, frames


READERS = {'libbet-board': libbet_session, 'springtrail-board': springtrail_session}


def ingest(name, folder, note):
    provenance, frames = READERS[name](Path(folder))
    png_total = sum(len(data_uri(frame['pixels'])) for frame in frames)
    runs_total = sum(path_runs_bytes(frame['pixels']) for frame in frames)
    chosen = 'indexed-png-data-uri' if png_total <= runs_total else 'path-runs'
    archive = dict(
        name=name,
        provenance=dict(note=note, **provenance),
        encoding=dict(chosen=chosen, frames=len(frames),
                      bytes_indexed_png=png_total, bytes_path_runs=runs_total,
                      measured_on='this captured sequence'),
        frames=[{key: value for key, value in frame.items() if key != 'pixels'}
                | {'png': data_uri(frame['pixels'])} for frame in frames])
    # The generator only draws the indexed-PNG payload; a sequence where the
    # rect runs won would need a rendering path that does not exist yet.
    assert chosen == 'indexed-png-data-uri', 'ENCODING_CHOICE'
    path = ARCHIVES / f'{name}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(archive, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(f'{path.relative_to(ROOT).as_posix()}: {len(frames)} frames, {path.stat().st_size} bytes; '
          f'indexed PNG {png_total} bytes vs rect runs {runs_total} bytes')
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('name', choices=tuple(READERS))
    parser.add_argument('folder', help='the retained session folder under workdir/')
    parser.add_argument('--note', required=True, help='one plain sentence of provenance for the wiki')
    args = parser.parse_args()
    ingest(args.name, args.folder, args.note)
    return 0


if __name__ == '__main__':
    sys.exit(main())
