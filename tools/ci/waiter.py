"""Read-only hosted waiter for authenticated, explicitly invoked local evidence."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from .github import GitHub
from .model import admit, config, latest_status, request, require

ROOT = Path(__file__).resolve().parents[2]


def wait(cfg, req, api, *, timeout=3300, poll=10, sleep=time.sleep, clock=time.monotonic):
    config(cfg); request(req)
    require(cfg['enabled'], 'trusted CI bootstrap is inactive')
    require(0 < timeout <= 3300 and 1 <= poll <= 60, 'bounded waiter timing')
    deadline = clock() + timeout
    initial = admit(cfg, req, api.snapshot(cfg, req, controller=False), initial=False, controller=False)
    while clock() < deadline:
        current = admit(cfg, req, api.snapshot(cfg, req, controller=False), initial=False, controller=False)
        require(current == initial, 'waiter attempt changed')
        status = latest_status(cfg, req, api.statuses(cfg, req), current['started'],
                               datetime.now(timezone.utc).isoformat())
        if status and status['state'] == 'success':
            # Recheck admission and the newest status immediately before acceptance.
            final = admit(cfg, req, api.snapshot(cfg, req, controller=False), initial=False, controller=False)
            require(final == current, 'waiter admission superseded')
            latest = latest_status(cfg, req, api.statuses(cfg, req), final['started'],
                                   datetime.now(timezone.utc).isoformat())
            require(latest == status, 'success superseded during acceptance')
            return {'status': 'PASS', 'scope': 'authenticated controller attestation; local artifacts not fetched',
                    'context': current['context'], 'status_id': status['id'],
                    'envelope_sha256': status['description'].removeprefix('attested sha256:')}
        if status and status['state'] in ('failure', 'error'):
            raise ValueError('controller reported failure')
        sleep(min(poll, max(0, deadline - clock())))
    raise ValueError('controller attestation timed out')


def main():
    try:
        cfg = config(json.loads((ROOT / 'cfg/trusted-ci.json').read_text(encoding='utf-8')))
        require(cfg['enabled'], 'trusted CI bootstrap is inactive; no licensed acceptance')
        req = request({'sha': os.environ['CI_SHA'], 'run_id': int(os.environ['CI_RUN_ID']),
                       'attempt': int(os.environ['CI_ATTEMPT']), 'profile': os.environ['CI_PROFILE']})
        result = wait(cfg, req, GitHub(os.environ.pop('GH_TOKEN', None)))
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
