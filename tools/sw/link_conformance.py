"""Actual pinned RGBDS linking plus an independent direct-header checksum oracle."""
import json
from pathlib import Path
import shutil
import subprocess
import uuid
from n2m.rgbds import install
from n2m.records import atomic_json, atomic_text, file_hash
from .assembler import assemble
from .linker import link
from .package import package


def proof(root, build, args, provenance):
    stage = build / 'sw/link-conformance'
    folder = stage / 'runs' / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True)
    report = {'status': 'FAIL', **provenance, 'commands': []}
    try:
        pin, tools, installation = install(root, stage / 'cache', args.offline)
        report['installation'] = installation
        source = root / 'src/sw/linker/conformance'
        inputs = list(source.glob('*')) + list((root / 'tools/sw').glob('*.py')) + list((root / 'tools/sw').glob('*.json'))
        inputs += [root / name for name in ['src/sw/generated/interfaces.inc', 'tools/n2m/generated_interfaces.py', 'cfg/interfaces.json', 'tools/n2m/rgbds.py', 'tools/n2m/records.py', 'tools/n2m/dependencies.json']]
        report['inputs'] = {p.relative_to(root).as_posix():file_hash(p) for p in inputs if p.is_file()}
        for name in ['main.asm','other.asm','main.rgbasm','other.rgbasm','layout.json']:
            shutil.copyfile(source / name, folder / name)
        objects = [(name,assemble(folder / name,folder,root / 'src/sw/generated/interfaces.inc')) for name in ['main.asm','other.asm']]
        for index,(_,obj) in enumerate(objects): atomic_json(folder / f'{index}.object.json',obj)
        linked = link(objects,json.loads((folder/'layout.json').read_text()),{'unit':'main.asm','symbol':'Start'})
        actual = bytearray(linked['image'])
        if args.mutate == 'relocation': actual[0x201] ^= 1
        (folder/'actual.bin').write_bytes(actual)
        def run(command,name):
            report['commands'].append([str(x) for x in command])
            result=subprocess.run(command,cwd=folder,text=True,encoding='utf-8',errors='replace',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
            atomic_text(folder/(name+'.log'),result.stdout)
            atomic_json(folder/(name+'.exit.json'),{'returncode':result.returncode})
            if result.returncode or 'warning:' in result.stdout.lower():raise ValueError(f'{name} failed: exit {result.returncode}')
            return result.stdout.strip()
        for name,tool in tools.items():
            if run([tool,'--version'],name+'-version') != name+' v'+pin['version']:raise ValueError('oracle version mismatch')
        for name in ['main','other']:
            run([tools['rgbasm'],'-Wall','-Werror','-o',folder/(name+'.o'),folder/(name+'.rgbasm')],'assemble-'+name)
        run([tools['rgblink'],'-p','255','-o',folder/'oracle.gb','-n',folder/'oracle.sym',folder/'main.o',folder/'other.o'],'link')
        expected=(folder/'oracle.gb').read_bytes()
        (folder/'expected.bin').write_bytes(expected)
        if actual != expected:
            offset=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)))
            raise ValueError(f'relocation mismatch offset={offset} actual={actual[offset]:02x} expected={expected[offset]:02x}')
        oracle_symbols={}
        for line in (folder/'oracle.sym').read_text().splitlines():
            fields=line.split()
            if len(fields)==2 and not line.startswith(';') and ':' in fields[0]:
                oracle_symbols[fields[1]]=int(fields[0].split(':')[1],16)
        selected=['Start','Partner','BranchForward','BranchBackward','TargetForward','TargetBackward','RamBuffer']
        checked={}
        for name in selected:
            value=next(s['value'] for s in linked['symbols']['symbols'] if s['symbol']==name and s['visibility']=='export')
            if value!=oracle_symbols[name]:raise ValueError('linked symbol mismatch: '+name)
            checked[name]=value
        atomic_json(folder/'symbols-compared.json',checked)
        rom=bytearray(package(linked,'LINK ORACLE',9))
        if args.mutate=='checksum':rom[0x14f]^=1
        (folder/'image.gb').write_bytes(rom)
        # Independent header construction uses fixed format offsets and an
        # iterative checksum, not package.py's summed formula or validator.
        header=bytearray(80);header[1]=195;header[2]=0;header[3]=2
        header[52:63]=b'LINK ORACLE';header[74]=1;header[76]=9
        checksum=0
        for value in header[52:77]:checksum=(checksum-value-1)%256
        header[77]=checksum
        independent=bytearray(expected);independent[256:336]=header
        total=0
        for offset,value in enumerate(independent):
            if offset not in (334,335):total=(total+value)%65536
        independent[334]=total//256;independent[335]=total%256
        (folder/'expected-package.gb').write_bytes(independent)
        if rom!=independent:raise ValueError('package checksum/header mismatch')
        report.update(status='PASS',linked_bytes=len(actual),selected_symbols=checked,relative_limits=[-128,127])
    except Exception as error:report['error']=str(error)
    if (stage/'cache').exists():shutil.copytree(stage/'cache',folder/'cache-snapshot')
    report['artifacts']={p.relative_to(root).as_posix():file_hash(p) for p in folder.rglob('*') if p.is_file()}
    atomic_json(folder/'result.json',report);atomic_json(stage/'result.json',report)
    return report
