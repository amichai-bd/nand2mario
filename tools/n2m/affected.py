"""Conservative advisory impact reports; never an execution or reuse verdict."""
import ast
import hashlib
import json
import subprocess
import time
from pathlib import Path

from . import catalogue, host_closure
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


def tracked_files(root, directory):
    """Tracked files under one declared directory input; untracked additions force fallback anyway."""
    return [p for p in git(root,'ls-files','-z','--',directory).decode().split('\0') if p]


def host_inputs(root, model, cache):
    """Declared host unit closures by name; an undeclared or unknown closure is absent."""
    inputs={}
    for name,entry in model['units'].items():
        if entry['kind']!='unit':continue
        try:inputs[name]=host_closure.closure(root,name,entry,model['external_imports'],cache,lambda d:tracked_files(root,d))
        except host_closure.Unknown:continue
    return inputs


def closures(root, model):
    """Every known input closure by unit name: declared host closures and simulation inputs.

    A simulation whose registry inputs cannot be listed is recorded in the
    second mapping by its error and stays selected."""
    names,_=catalogue.select(model,level=2)
    definitions=json.loads((root/'src/dv/builder/targets.json').read_text(encoding='utf-8'))
    inputs=host_inputs(root,model,{}); errors={}
    for name in names:
        if model['units'][name]['kind']!='sim':continue
        try:inputs[name]=target_inputs(root,definitions[name])
        except (ValueError,OSError,KeyError) as error:errors[name]=str(error)
    return inputs,errors


def decide(root, model, changed, same, known=None, only=None):
    """(fallback, units) for one change set; the whole advisory decision, free of Git.

    `changed` is the `changes()` row list and `same(path)` returns the
    (current, base) hash pair of one closure path. `tests affected` supplies
    both from Git and decides every unit; the mutation proof supplies a single
    differing path and, through `only`, decides just the recorded detectors,
    because each undecided simulation costs a registry validation."""
    root=Path(root).resolve()
    names,_=catalogue.select(model,level=2)
    if only is not None:names=[n for n in names if n in only]
    paths={r['path'] for r in changed}|{r['old_path'] for r in changed if 'old_path' in r}
    inputs,errors=known or closures(root,model)
    known_paths=set(model['units'])|set().union(*inputs.values())
    fallback=[]
    if any(r['status']!='M' for r in changed):fallback.append('new, deleted or renamed paths require full impact review')
    if paths-known_paths:fallback.append('unmapped changed paths: '+', '.join(sorted(paths-known_paths)))
    if any(p.startswith(('tools/','cfg/','.github/')) or p in ('src/dv/builder/targets.json',catalogue.CATALOGUE) for p in paths):
        fallback.append('tool, configuration or catalogue change can affect preparation and execution')
    units={}
    for name in names:
        row=dict(decision='selected',reasons=[])
        host=model['units'][name]['kind']=='unit'
        if host and name not in inputs:
            row['reasons']=['unknown closure: no declared inputs in '+catalogue.CATALOGUE]
        elif fallback:row['reasons']=fallback[:]
        elif name in errors:row['reasons']=['input validation: '+errors[name]]
        elif paths&inputs[name]:row['reasons']=['changed inputs: '+', '.join(sorted(paths&inputs[name]))]
        else:
            try:
                # A host unit's declared closure is validated by `tests validate`; a simulation
                # target also needs its call-free qualification before its inputs count as complete.
                unknown=None if host else uncertainty(root,load_target(root,name)[0])
                if unknown:row['reasons']=[unknown]
                else:
                    hashes={p:same(p)[0] for p in sorted(inputs[name])}
                    if all(current==base for current,base in map(same,hashes)):
                        reason='validated declared host closure equal base' if host else 'validated declared repository inputs equal base'
                        row.update(decision='review_candidate',reasons=[reason],inputs=hashes,
                                   limitation='not accepted reuse; prior result, tool/runtime identity and scoped gates still require review')
                    else:row['reasons']=['input bytes differ from base']
            except (ValueError,OSError,KeyError,StopIteration,SyntaxError,subprocess.CalledProcessError) as error:
                row['reasons']=['dependency qualification failed: '+str(error)]
        units[name]=row
    return fallback,units


def report(root, base):
    started=time.monotonic(); root=Path(root).resolve()
    commit,changed=changes(root,base)
    model,_=catalogue.load(root)
    problems=catalogue.coverage(root,model)
    if problems:raise ValueError(problems[0])
    # Units share most closure files, so each path is hashed and compared to the base once.
    equal_to_base={}
    def same(path):
        if path not in equal_to_base:
            equal_to_base[path]=(file_hash(root/path),hashlib.sha256(git(root,'show',commit+':'+path)).hexdigest())
        return equal_to_base[path]
    fallback,units=decide(root,model,changed,same)
    return dict(status='PASS',scope='advisory only; no tests executed or evidence reused',base=commit,
                head=git(root,'rev-parse','HEAD').decode().strip(),changes=changed,fallback=fallback,
                required_checks='unchanged; follow the existing PR required suite',units=units,
                selected=sum(r['decision']=='selected' for r in units.values()),
                review_candidates=sum(r['decision']=='review_candidate' for r in units.values()),
                elapsed_seconds=time.monotonic()-started)
