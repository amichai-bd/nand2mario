"""Conservative advisory impact reports; never an execution or reuse verdict."""
import ast
import hashlib
import json
import subprocess
import time
from pathlib import Path

from . import catalogue
from .hdl import dependencies
from .records import file_hash
from .simulation import load_target


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE, timeout=30)


def changes(root, base):
    commit = git(root, 'rev-parse', '--verify', '--end-of-options', base+'^{commit}').decode().strip()
    fields = git(root, 'diff', '--name-status', '-z', '--find-renames', commit, '--').decode().split('\0')
    rows=[]; i=0
    while i < len(fields) and fields[i]:
        status=fields[i]; path=fields[i+1]; i+=2
        row=dict(status=status, path=path)
        if status.startswith(('R','C')):
            row['old_path']=path; row['path']=fields[i]; i+=1
        rows.append(row)
    rows += [dict(status='A',path=p) for p in git(root,'ls-files','--others','--exclude-standard','-z').decode().split('\0') if p]
    return commit, rows


def target_inputs(root, target):
    """The repository-file portion of simulation.simulate's fingerprint."""
    paths=set(dependencies(root,target['sources']))
    paths.update(('src/dv/builder/targets.json','tools/build.py','tools/n2m/dependencies.json'))
    paths.update(p.relative_to(root).as_posix() for p in (root/'tools/n2m').glob('*.py'))
    if 'driver' in target:
        driver=target['driver']; paths.update((driver['script'],driver['peer'],*driver['inputs']))
    if target.get('testbench')=='python':
        paths.update(target['python']['inputs'])
        paths.update(('src/dv/python/requirements.txt','src/dv/python/THIRD_PARTY.md'))
    return paths


def uncertainty(root, target):
    """A positive call-free subset, not a general Python dependency analyzer."""
    if target.get('testbench')!='python' or target.get('preload') or target.get('driver'):
        return 'preload, driver or non-Python dependency qualification remains manual'
    modules={Path(p).stem for p in target['python']['inputs'] if p.endswith('.py')}
    for path in target['python']['inputs']:
        if not path.endswith('.py'):continue
        tree=ast.parse((root/path).read_text(encoding='utf-8'),filename=path)
        decorators=set()
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if (isinstance(decorator,ast.Call) and not decorator.args and not decorator.keywords
                            and isinstance(decorator.func,ast.Attribute) and decorator.func.attr=='test'
                            and isinstance(decorator.func.value,ast.Name) and decorator.func.value.id=='cocotb'):
                        decorators.update((decorator,decorator.func))
                    else:return f'unqualified decorator dependency: {path}'
            if isinstance(node,ast.ImportFrom):
                if node.level or not node.module or any(a.name=='*' for a in node.names):
                    return f'unqualified relative or wildcard import: {path}'
                imports={node.module.split('.')[0]}
            elif isinstance(node,ast.Import):imports={a.name.split('.')[0] for a in node.names}
            else:continue
            if imports-modules-{'cocotb'}:
                return f'unqualified external or unresolved import: {path}'
        for node in ast.walk(tree):
            if (isinstance(node,ast.Name) and node.id=='cocotb' and isinstance(node.ctx,ast.Store)
                    or isinstance(node,ast.arg) and node.arg=='cocotb'):
                return f'unqualified entry-decorator shadowing: {path}'
            if isinstance(node,(ast.Call,ast.Attribute)) and node not in decorators:
                return f'unqualified call or attribute dependency: {path}'
            if isinstance(node,(ast.ClassDef,ast.With,ast.AsyncWith,ast.Lambda,ast.ListComp,
                                ast.SetComp,ast.DictComp,ast.GeneratorExp,ast.For,ast.AsyncFor,
                                ast.Await,ast.YieldFrom)):
                return f'unqualified implicit callable dependency: {path}'
    return None


def report(root, base):
    started=time.monotonic(); root=Path(root).resolve()
    commit,changed=changes(root,base)
    model,_=catalogue.load(root)
    problems=catalogue.coverage(root,model)
    if problems:raise ValueError(problems[0])
    names,_=catalogue.select(model,level=2)
    paths={r['path'] for r in changed}|{r['old_path'] for r in changed if 'old_path' in r}
    definitions=json.loads((root/'src/dv/builder/targets.json').read_text(encoding='utf-8'))
    inputs={}; errors={}
    for name in names:
        if model['units'][name]['kind']!='sim':continue
        try:inputs[name]=target_inputs(root,definitions[name])
        except (ValueError,OSError,KeyError) as error:errors[name]=str(error)
    known=set(model['units'])|set().union(*inputs.values())
    fallback=[]
    if any(r['status']!='M' for r in changed):fallback.append('new, deleted or renamed paths require full impact review')
    if paths-known:fallback.append('unmapped changed paths: '+', '.join(sorted(paths-known)))
    if any(p.startswith(('tools/','cfg/','.github/')) or p in ('src/dv/builder/targets.json',catalogue.CATALOGUE) for p in paths):
        fallback.append('tool, configuration or catalogue change can affect preparation and execution')
    units={}
    for name in names:
        row=dict(decision='selected',reasons=[])
        if model['units'][name]['kind']=='unit':
            row['reasons']=['standalone host dependency closure is unknown']
        elif fallback:row['reasons']=fallback[:]
        elif name in errors:row['reasons']=['input validation: '+errors[name]]
        elif paths&inputs[name]:row['reasons']=['changed inputs: '+', '.join(sorted(paths&inputs[name]))]
        else:
            try:
                target=definitions[name]
                unknown=uncertainty(root,target)
                if unknown:row['reasons']=[unknown]
                else:
                    load_target(root,name)
                    hashes={p:file_hash(root/p) for p in sorted(inputs[name])}
                    equal=all(hashlib.sha256(git(root,'show',commit+':'+p)).hexdigest()==h for p,h in hashes.items())
                    if equal:
                        row.update(decision='review_candidate',reasons=['validated declared repository inputs equal base'],inputs=hashes,
                                   limitation='not accepted reuse; prior result, tool/runtime identity and scoped gates still require review')
                    else:row['reasons']=['input bytes differ from base']
            except (ValueError,OSError,KeyError,StopIteration,SyntaxError,subprocess.CalledProcessError) as error:
                row['reasons']=['dependency qualification failed: '+str(error)]
        units[name]=row
    return dict(status='PASS',scope='advisory only; no tests executed or evidence reused',base=commit,
                head=git(root,'rev-parse','HEAD').decode().strip(),changes=changed,fallback=fallback,
                required_checks='unchanged; follow the existing PR required suite',units=units,
                selected=sum(r['decision']=='selected' for r in units.values()),
                review_candidates=sum(r['decision']=='review_candidate' for r in units.values()),
                elapsed_seconds=time.monotonic()-started)
