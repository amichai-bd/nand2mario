"""Bounded GitHub REST transport. Tokens stay in this process, never child argv."""
import json
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import quote
from .model import require


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('GitHub API redirect rejected')


class GitHub:
    def __init__(self, token):
        require(isinstance(token, str) and bool(token), 'local API token missing')
        self.token = token
        self.opener = build_opener(NoRedirect())

    def call(self, path, body=None):
        require(path.startswith('/') and '://' not in path and '\\' not in path, 'fixed API path')
        req = Request('https://api.github.com' + path,
                      data=None if body is None else json.dumps(body).encode('utf-8'),
                      headers={'Authorization': 'Bearer ' + self.token,
                               'Accept': 'application/vnd.github+json',
                               'X-GitHub-Api-Version': '2026-03-10',
                               'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=30) as response:
            raw = response.read(8_000_001)
        require(len(raw) <= 8_000_000, 'API response bound')
        return json.loads(raw)

    def pages(self, path, key=None):
        values = []
        for page in range(1, 101):
            data = self.call(path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
            items = data if key is None else data[key]
            require(type(items) is list, 'API list response')
            values += items
            if len(items) < 100:
                return values
        raise ValueError('API pagination bound reached')

    def statuses(self, cfg, req):
        return self.pages(f"/repos/{cfg['repository']}/commits/{req['sha']}/statuses")

    def snapshot(self, cfg, req, *, controller=True):
        base = f"/repos/{cfg['repository']}"
        run = f"{base}/actions/runs/{req['run_id']}"
        branch = self.call(base + '/branches/main')
        return {
            'repository': self.call(base),
            'account': self.call('/user') if controller else None,
            'workflow': self.call(base + f"/actions/workflows/{cfg['workflow_id']}"),
            'workflow_blob': self.call(base + '/contents/' + cfg['workflow_path'] +
                                       '?ref=' + req['sha'])['sha'],
            'run': self.call(run),
            'attempt': self.call(run + f"/attempts/{req['attempt']}"),
            'jobs': self.pages(run + f"/attempts/{req['attempt']}/jobs", 'jobs'),
            'branch': branch,
            'ancestry': self.call(base + f"/compare/{req['sha']}...{branch['commit']['sha']}")['status'],
            'environment': self.call(base + '/environments/' + quote(cfg['environment'], safe='')),
            'branch_policies': self.pages(base + '/environments/' + cfg['environment'] +
                                          '/deployment-branch-policies', 'branch_policies'),
        }

    def post(self, cfg, req, state, description, context, url):
        return self.call(f"/repos/{cfg['repository']}/statuses/{req['sha']}",
                         {'state': state, 'description': description,
                          'context': context, 'target_url': url})
