"""Compare retained DUT observations with independent Core; preserve timing gaps."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.n2m.interface_codec import unpack_record
from src.dv.sameboy.retirement import compare, fields, project


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core',type=Path)
    parser.add_argument('dut',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    log=args.core.read_text()
    reference=project(log)
    with (args.dut/'retirement.csv').open() as stream:
        actual=[unpack_record('retirement',bytes.fromhex(row['record'])[::-1]) for row in csv.DictReader(stream)]
    compare(reference,actual)
    with (args.dut/'pixels.csv').open() as stream:
        dut=[{k:int(v) for k,v in row.items()} for row in csv.DictReader(stream)]
    visible=[];raw=[];enable=[]
    for line in log.splitlines():
        if line.startswith('visible '):
            parts=dict(part.split('=') for part in line.split()[1:])
            visible.append({k:int(v,16 if k=='rgb' else 10) for k,v in parts.items()})
        elif line.startswith('pixel '):
            parts=dict(part.split('=') for part in line.split()[1:])
            raw.append({k:int(v,16 if k=='rgb' else 10) for k,v in parts.items()})
        elif line.startswith('write '):
            row=fields(line)
            if row['address']==0xff40 and row['data']==0x91:enable.append(row['dot'])
    # The configured upstream GB_PALETTE_GREY is a display encoding, not a DUT oracle.
    shades={0xffffff:0,0xaaaaaa:1,0x555555:2,0x000000:3}
    if len(visible)!=len(dut) or len(raw)!=len(dut):raise ValueError('pixel observation count differs')
    first_time=None
    for index,(screen,pixel,observed) in enumerate(zip(visible,raw,dut,strict=True)):
        expected=(screen['frame'],screen['y']*160+screen['x'],shades[screen['rgb']])
        actual=(observed['frame'],observed['index'],observed['shade'])
        if expected!=actual:raise ValueError(f'pixel {index}: expected={expected} actual={actual}')
        if (pixel['x'],pixel['y'])!=(screen['x'],screen['y']):raise ValueError('raw/public pixel order differs')
        ticks=pixel['native_ticks8mhz']-pixel['pending_display_ticks8mhz']
        if ticks%2:raise ValueError('fractional native PPU action')
        native_action=ticks//2
        # Preserve the source action identity; do not fit an offset to the DUT.
        if first_time is None and native_action!=observed['dot']-1:
            first_time={'frame':observed['frame'],'index':observed['index'],
                        'core_action_dot':native_action,'dut_preedge_dot':observed['dot']-1,
                        'core_enable_action_dot':enable[0],
                        'dut_enable_preedge_dot':591,
                        'core_relative':native_action-enable[0],
                        'dut_relative':observed['dot']-1-591}
    paths=[args.core,args.dut/'retirement.csv',args.dut/'pixels.csv',Path(__file__),Path(__file__).with_name('retirement.py')]
    report={'command':sys.argv,'input_sha256':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'status':'TIMING_MISMATCH_UNRESOLVED','scope':'historical DUT diagnostic; not current-head acceptance',
            'retirement_records_exact':len(reference),'visible_pixels_exact':len(visible),
            'first_pixel_timing_difference':first_time,
            'normal_frame_first':{'core_action':(raw[23040]['native_ticks8mhz']-raw[23040]['pending_display_ticks8mhz'])//2,
                                  'dut_completed':dut[23040]['dot']}}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 1 if first_time else 0


if __name__=='__main__':raise SystemExit(main())
