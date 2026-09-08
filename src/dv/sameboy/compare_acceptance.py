"""Check exact retirement fields and every ordered visible pixel for #102."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from src.dv.sameboy.compare_diagnostic import compare_values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core',type=Path)
    parser.add_argument('dut',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    paths=[args.core,args.dut/'retirement.csv',args.dut/'pixels.csv',Path(__file__),
           Path(__file__).with_name('compare_diagnostic.py'),Path(__file__).with_name('retirement.py'),
           Path(__file__).with_name('scenario.json'),ROOT/'cfg/interfaces.json']
    report={'command':sys.argv,'input_sha256':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            'scope':'exact retirement ABI and ordered visible pixel values; DUT timing checks remain separate; #194 timing diagnostic is unresolved'}
    try:
        records,visible,_,_,_=compare_values(args.core.read_text(),args.dut)
        if len(records)!=69 or len(visible)!=46080:
            raise ValueError(f'selected program completion: expected=(69, 46080) actual=({len(records)}, {len(visible)})')
        for index,pixel in enumerate(visible):
            if (pixel['frame'],pixel['x'],pixel['y'])!=(index//23040,index%160,(index%23040)//160):
                raise ValueError(f'reference visible pixel order at {index}')
        report.update(status='PASS',retirement_records_exact=len(records),visible_pixels_exact=len(visible))
    except (ValueError,KeyError) as error:
        report.update(status='FAIL',mismatch=str(error))
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
