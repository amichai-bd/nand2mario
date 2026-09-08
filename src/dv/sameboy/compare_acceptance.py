"""Check exact retirement fields and every ordered visible pixel for #102."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from src.dv.sameboy.compare_diagnostic import compare_values
from tools.n2m.records import cache_matches, digest, file_hash
from tools.n2m.preload import verify as verify_preload


def require_producers(core, dut):
    """Bind observations to successful original-image producers and current inputs."""
    core=core.resolve();dut=dut.resolve()
    native=json.loads((core.parent/'result.json').read_text())
    hardware=json.loads((dut/'result.json').read_text())
    if native.get('status')!='PASS' or hardware.get('status')!='PASS':
        raise ValueError('producer status: expected=PASS for Core and DUT')
    manifest=json.loads((Path(__file__).parent/'sources.json').read_text())
    if native.get('pin')!=manifest['pin'] or native.get('observation_mode')!='observed-cycle-path':
        raise ValueError('Core model/observation mode differs')
    if not native.get('commands') or any(c['returncode']!=0 for c in native['commands']):
        raise ValueError('Core command failed')
    expected={'Core/'+name:value for name,value in manifest['files'].items()}
    for name in ('profile.c','probe.c','observe.patch','sources.json','scenario.json','retirement.py','probe.py'):
        path=Path(__file__).with_name(name).resolve()
        expected[str(path)]=file_hash(path)
    expected[str(ROOT/'cfg/interfaces.json')]=file_hash(ROOT/'cfg/interfaces.json')
    inputs=native['inputs']
    image_keys=set(inputs)-set(expected)
    if len(image_keys)!=1 or inputs[next(iter(image_keys))]!=manifest['image']['sha256']:
        raise ValueError('Core image identity differs')
    if any(inputs.get(name)!=value for name,value in expected.items()):
        raise ValueError('Core source/profile/ABI inputs differ')
    if core.name!='observations.log' or not cache_matches(native,digest(inputs),core.parent,core.parent):
        raise ValueError('Core producer artifacts differ')
    if native['artifacts'].get(core.name)!=file_hash(core):
        raise ValueError('Core observation not bound to producer')
    if not cache_matches(hardware,hardware.get('fingerprint'),ROOT):
        raise ValueError('DUT producer artifacts differ')
    definition=json.loads((ROOT/'src/dv/builder/targets.json').read_text())['python-integration']
    if hardware['options']['definition']!=definition or hardware['python_results']['status']!='PASS':
        raise ValueError('DUT target/model/preload result differs')
    if any(c['exit_code']!=0 for c in hardware['commands']):
        raise ValueError('DUT command failed')
    if any(file_hash(ROOT/name)!=value for name,value in hardware['inputs'].items()):
        raise ValueError('DUT source/configuration inputs differ')
    for name in ('retirement.csv','pixels.csv','preload.json'):
        key=(dut/name).relative_to(ROOT).as_posix()
        if hardware['artifacts'].get(key)!=file_hash(dut/name):
            raise ValueError('DUT observation not bound to producer: '+name)
    preload=verify_preload(dut)
    if preload['image_sha256']!=manifest['image']['sha256'] or preload['image_bytes']!=manifest['image']['length']:
        raise ValueError('DUT image identity differs')
    return [core.parent/'result.json',dut/'result.json',dut/'preload.json']


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
            'scope':'exact retirement ABI and ordered visible pixel values; DUT timing checks remain separate; #197 timing diagnostic is unresolved'}
    try:
        producers=require_producers(args.core,args.dut)
        report['producer_sha256']={str(p):file_hash(p) for p in producers}
        records,visible,_,_,_=compare_values(args.core.read_text(),args.dut)
        if len(records)!=69 or len(visible)!=46080:
            raise ValueError(f'selected program completion: expected=(69, 46080) actual=({len(records)}, {len(visible)})')
        for index,pixel in enumerate(visible):
            if (pixel['frame'],pixel['x'],pixel['y'])!=(index//23040,index%160,(index%23040)//160):
                raise ValueError(f'reference visible pixel order at {index}')
        report.update(status='PASS',retirement_records_exact=len(records),visible_pixels_exact=len(visible))
    except (ValueError,KeyError,OSError) as error:
        report.update(status='FAIL',mismatch=str(error))
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
