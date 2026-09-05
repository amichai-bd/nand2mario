"""Shared strict target shape/metadata boundary for assembly and packaging."""
from pathlib import PurePosixPath
import re
from n2m.generated_interfaces import PROFILE_NAME
from .expressions import AssemblyError

BASE = {'directory', 'sources', 'assets'}
PACKAGE = {'layout', 'entry', 'title', 'version', 'profile', 'interface_schema_version'}


def validate_target(target, require_package=False, stage='assemble'):
    def reject(cause, code='SCHEMA_MISMATCH'):
        error=AssemblyError(code,cause,{'file':'targets.json','line':1,'column':1})
        error.diagnostic['stage']=stage
        raise error
    def path(value):
        return (type(value) is str and bool(value) and not value.startswith('/') and ':' not in value
                and '\\' not in value and '..' not in PurePosixPath(value).parts)
    if type(target) is not dict or not BASE<=target.keys() or target.keys()-BASE-PACKAGE:
        reject('unknown or malformed software target')
    if not path(target['directory']) or type(target['sources']) is not list or not target['sources'] or not all(path(s) for s in target['sources']):
        reject('nonempty relative directory/source paths required','PRIVATE_PATH')
    if len(target['sources'])!=len(set(target['sources'])):
        reject('duplicate source spelling')
    if type(target['assets']) is not dict or not all(type(n) is str and n and path(p) for n,p in target['assets'].items()):
        reject('declared asset names and paths required')
    present=target.keys() & PACKAGE
    if present and present!=PACKAGE or require_package and present!=PACKAGE:
        reject('packaging metadata must be absent or complete')
    if present:
        if not path(target['layout']):reject('confined layout path required','PRIVATE_PATH')
        entry=target['entry']
        if (type(entry) is not dict or set(entry)!={'unit','symbol'} or type(entry['unit']) is not str
                or entry['unit'] not in target['sources'] or type(entry['symbol']) is not str
                or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',entry['symbol'])):
            reject('entry requires a declared source unit and symbol')
        if type(target['title']) is not str or not re.fullmatch('[A-Z0-9 ]{1,15}',target['title']):
            reject('invalid direct-profile title','METADATA')
        if type(target['version']) is not int or not 0<=target['version']<=255:
            reject('version must be an explicit byte','METADATA')
        if target['profile']!=PROFILE_NAME or target['profile']!='dmg-direct-v1':
            reject('unsupported target profile','PROFILE_MISMATCH')
        if type(target['interface_schema_version']) is not int or target['interface_schema_version']!=1:
            reject('unsupported interface schema identity')
    return target
