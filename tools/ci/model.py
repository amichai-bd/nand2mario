"""Closed trust predicates shared by the local controller and hosted waiter."""
from datetime import datetime, timezone
import hashlib
import json
import re

PROFILES = {
    'questa-baseline': ('baseline-good', 'baseline-broken'),
    'quartus-clocking': ('clocking-nominal', 'clocking-invalid'),
}
CONFIG_KEYS = {'schema', 'enabled', 'repository', 'repository_id', 'controller_id',
               'workflow_id', 'workflow_path', 'workflow_blob', 'environment'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def config(value):
    require(type(value) is dict and set(value) == CONFIG_KEYS, 'closed configuration schema')
    require(value['schema'] == 1 and type(value['enabled']) is bool, 'configuration version/enable')
    require(re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', value['repository']) is not None,
            'repository name')
    for field in ('repository_id', 'controller_id', 'workflow_id'):
        require(type(value[field]) is int and value[field] >= (1 if value['enabled'] else 0), field)
    require(value['workflow_path'] == '.github/workflows/trusted-product.yml', 'workflow path')
    require(re.fullmatch('[0-9a-f]{40}', value['workflow_blob']) is not None, 'workflow blob')
    require(value['environment'] == 'trusted-product', 'environment identity')
    return value


def request(value):
    require(type(value) is dict and set(value) == {'sha', 'run_id', 'attempt', 'profile'},
            'closed invocation schema: remote commands/paths are unavailable')
    require(re.fullmatch('[0-9a-f]{40}', value['sha']) is not None, 'exact source SHA')
    for field in ('run_id', 'attempt'):
        require(type(value[field]) is int and value[field] > 0, field)
    require(value['profile'] in PROFILES, 'fixed profile')
    return value


def context(req):
    request(req)
    return f"n2m/trusted/{req['run_id']}/{req['attempt']}/{req['profile']}"


def run_url(cfg, req):
    return f"https://github.com/{cfg['repository']}/actions/runs/{req['run_id']}/attempts/{req['attempt']}"


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, 'timestamp timezone')
    return parsed.astimezone(timezone.utc)


def admit(cfg, req, snapshot, *, initial, controller=True):
    config(cfg); request(req)
    require(cfg['enabled'], 'trusted CI bootstrap is inactive')
    repo, run, attempt = snapshot['repository'], snapshot['run'], snapshot['attempt']
    require(repo['id'] == cfg['repository_id'] and repo['full_name'] == cfg['repository'],
            'repository identity')
    if controller:
        require(snapshot['account']['id'] == cfg['controller_id'], 'controller identity')
    workflow = snapshot['workflow']
    require(workflow['id'] == cfg['workflow_id'] and workflow['path'] == cfg['workflow_path']
            and workflow['state'] == 'active', 'workflow identity')
    require(snapshot['workflow_blob'] == cfg['workflow_blob'], 'immutable workflow source')
    for item in (run, attempt):
        require(item['id'] == req['run_id'] and item['run_attempt'] == req['attempt']
                and item['head_sha'] == req['sha'] and item['head_branch'] == 'main'
                and item['workflow_id'] == cfg['workflow_id']
                and item['event'] == 'workflow_dispatch' and item['status'] == 'in_progress'
                and item['conclusion'] is None, 'active exact run/attempt')
        require(item['repository']['id'] == cfg['repository_id']
                and item['head_repository']['id'] == cfg['repository_id'], 'run repository')
        require(item['actor']['id'] == cfg['controller_id']
                and item['triggering_actor']['id'] == cfg['controller_id'], 'dispatch account')
    jobs = snapshot['jobs']
    expected = f"Trusted product attestation ({req['profile']})"
    require(len(jobs) == 1 and jobs[0]['name'] == expected
            and jobs[0]['run_id'] == req['run_id'] and jobs[0]['run_attempt'] == req['attempt']
            and jobs[0]['head_sha'] == req['sha'] and jobs[0]['status'] == 'in_progress'
            and jobs[0]['conclusion'] is None, 'one active expected waiter job')
    branch = snapshot['branch']
    require(branch['name'] == 'main' and branch['protected'] is True, 'protected main')
    if initial:
        require(branch['commit']['sha'] == req['sha'], 'initial current main SHA')
    else:
        require(snapshot['ancestry'] in ('identical', 'ahead'), 'admitted SHA remains on main')
    env = snapshot['environment']
    require(env['name'] == cfg['environment'] and env['deployment_branch_policy'] ==
            {'protected_branches': False, 'custom_branch_policies': True}, 'environment branch policy')
    require([(p['name'], p['type']) for p in snapshot['branch_policies']] == [('main', 'branch')],
            'environment permits only main branch')
    start = timestamp(attempt['run_started_at'])
    require(start <= timestamp(jobs[0]['started_at']), 'attempt/job time ordering')
    return {'context': context(req), 'url': run_url(cfg, req),
            'started': attempt['run_started_at'], 'job_id': jobs[0]['id']}


def latest_status(cfg, req, statuses, started, now):
    """Accept no older success behind a newer pending, failure or foreign status."""
    relevant = [s for s in statuses if s['context'] == context(req)]
    if not relevant:
        return None
    ids = [s['id'] for s in relevant]
    require(all(type(i) is int and i > 0 for i in ids) and len(set(ids)) == len(ids),
            'ambiguous status inventory')
    newest = max(relevant, key=lambda s: s['id'])
    require(all(timestamp(s['created_at']) <= timestamp(newest['created_at']) for s in relevant),
            'ambiguous status chronology')
    require(newest['creator']['id'] == cfg['controller_id'], 'status creator')
    require(newest['target_url'] == run_url(cfg, req), 'status run URL')
    require(timestamp(started) <= timestamp(newest['created_at']) <= timestamp(now),
            'status current attempt time window')
    require(newest['state'] in ('pending', 'success', 'failure', 'error'), 'status state')
    if newest['state'] == 'success':
        require(re.fullmatch(r'attested sha256:[0-9a-f]{64}', newest['description']) is not None,
                'canonical envelope digest attestation')
    return newest
