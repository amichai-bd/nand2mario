# Branches and pull requests

Follow the [agent work rules](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md#work)
for branch naming, worktree ownership, draft state, and issue scope.
Use a lowercase branch slug, such as `42-fix-timer`.
Each closing reference has its own line:

```text
Closes #<issue-number>
```

The issue owns the goal; the PR describes the result and evidence. Use the
[PR skill](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/pr-author/SKILL.md) for temporary body files and
the [agent flow](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/agent-flow/SKILL.md) for babysitting,
independent review, author undrafting, squash merge, and root cleanup.

## Scoped implementation and milestones

An implementation PR closes its own independently useful issue. Its criteria
select the applicable [verification tiers](../src/dv/integration/SPEC.md#verification-tiers);
full milestone acceptance belongs to named open milestone issues, referenced in
the PR. With scope authorization, revise existing issue boundaries explicitly:
state what lands, its required proof, and what remains in each open issue. Do not
label a partial subsystem or milestone complete. A known defect that undermines
the scoped result still blocks that PR, and introduced regressions remain its
responsibility. Finish the finite checklist and merge when scoped acceptance,
required validation, independent current-head review and conversations are satisfied.

## Policy and protection

The `PR policy` check requires a valid numbered branch, `main` base, and closing
references to open assigned issues including the primary branch issue. Only the
fixed [checkpoint exceptions](#checkpoint-exceptions) below may use matching
checkpoint and `Refs` lines without a closing reference, and only the
[automated statistics refresh](#automated-statistics-refresh) may merge without
independent review. Other PRs close their issues. It is the only check that
runs automatically on a pull request.

Main requires a passing up-to-date `PR policy` check, linear history, and resolved
review conversations. Force pushes and branch deletion are blocked on main. Human
approval is not required. Independent review and code/spec alignment are agent
responsibilities; they are not enforced by scripts or approval counts.

A merge closes its closing references and triggers Pages deployment. A trigger is not
proof that publication succeeded. See
[GitHub issue linking](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue).

## Hosted and local checks

The repository is private, so hosted runner minutes are billed. Only two
workflows run automatically:

- `PR policy` on every pull request event: metadata only, a few seconds, no
  build or test.
- `Pages` on every push to `main`: the issue-helper tests, then
  `python tools/wiki/check.py --browser --install-browser` before publication.
  It is the last hosted gate on the wiki.

Everything else runs locally before merge. The
[Builder](https://github.com/amichai-bd/nand2mario/blob/main/.github/workflows/builder.yml),
[Tile pixel](https://github.com/amichai-bd/nand2mario/blob/main/.github/workflows/tile-pixel.yml)
and [Wiki](https://github.com/amichai-bd/nand2mario/blob/main/.github/workflows/wiki.yml)
workflows keep their command sequences and run only by `workflow_dispatch`
(`gh workflow run <file> --ref <branch>`), for a second opinion on a clean
runner when an author or reviewer asks for one.

Before undrafting, the author runs from the worktree root, on the reviewed head,
and records commands and results in the PR:

```text
python tools/wiki/check.py --browser
python -m unittest discover -s .agents/skills/issue-author/scripts -p test_create_issue.py -v
python -m unittest discover -s .agents/skills/rtl-coder/scripts -p test_check_sv_style.py -v
python .agents/skills/rtl-coder/scripts/check_sv_style.py
```

These replace the former `Wiki check`. Add `--install-browser` on the first
wiki run. Then, by changed scope:

- Any change under `tools/`, `cfg/`, `src/sw/`, `src/dv/springtrail/`,
  `src/rtl/interfaces/`, `wiki/cfg/` or `.github/workflows/pr-policy.yml` runs
  the Builder sequence:

  ```text
  python tools/n2m/interfaces.py --check
  python tools/build.py check --tag ci-check --json
  python -m unittest discover -s tools/ci/tests -v
  python tools/build.py sw oracle --tag ci-rgbds --json
  python tools/build.py sw assemble assembler-basic --tag ci-assembler --json
  python tools/build.py sw conformance --tag ci-conformance --json
  python tools/build.py sw build linker-basic --tag ci-linker --json
  python tools/build.py sw link-conformance --tag ci-link-proof --json
  python tools/build.py sw asset-conformance --tag ci-assets --json
  ```

  followed by the deliberate `--mutate` runs, their expected manifest errors
  and the Springtrail host-fixture loader exactly as written in
  `builder.yml`; each mutation must fail with the recorded error. The manifest
  asserts and the fixture loader exist only inline in `builder.yml`; run them
  through git-bash, not PowerShell. `sw oracle` selects the RGBDS package for
  the local host, so the pinned Linux package in `tools/n2m/dependencies.json`
  is exercised only by an explicit dispatch of `builder.yml`; dispatch it on
  any change to `tools/n2m/dependencies.json` or `tools/n2m/rgbds.py`.
- Any change under `tools/sim/` or `src/rtl/display/` runs
  `python -m unittest discover -s tools/sim -p test_tile_pixel.py -v`.
- The scoped [verification tier](../src/dv/integration/SPEC.md#verification-tiers)
  supplies simulation, FPGA and hardware evidence; no hosted job ever ran those.
  Run a [declared subset](../tools/n2m/SPEC.md#regression-subsets) rather than
  naming targets by hand: `python tools/build.py regress pre-merge --tag <tag> --json`
  is the short ordinary set, and `composed-smoke` the bounded composed candidate.

A failure in any of these blocks the merge exactly as a red hosted check did.
Reuse results only for an unchanged head with unchanged relevant inputs.

## Checkpoint exceptions

This set is closed. It is a record of PRs the user authorized to merge without a
closing reference, each carrying matching `Checkpoint for #<number>` and
`Refs #<number>` lines for the issue it referenced when it merged. It authorizes
no further checkpoint, and no PR may be added to it.

The set is PR162, PR163, PR167, PR169 and PR179, all merged.

Each kept its acceptance in the issue it referenced when it merged; whether that
issue is still open today is a question for that issue, not for this record. The
pairing itself is not repeated here: the `PR policy` check holds it in its own
fixed map, keyed by PR number, and each PR body carries its own `Checkpoint for`
and `Refs` lines. That map is also why the set cannot grow by editing this page.

Every other PR closes its branch's issue, except the
[automated statistics refresh](#automated-statistics-refresh). A PR that merely
references an issue without closing it, outside this set and that class, does
not satisfy the policy.

## Automated statistics refresh

The owner authorized on 2026-09-11 one class of pull request that lands without
an agent, an independent review or a closing reference: the regenerated
[statistics snapshot](../project-statistics.md#refresh-the-snapshot). It is the
sole exemption from independent review. A regenerated `wiki/statistics.html`
needs no judgement, and the exemption is mechanically bounded: `PR policy`
accepts the class only when every field below matches, and the changed-file set
is read from the PR files API rather than from the description.

| Field | Required form |
| --- | --- |
| Branch | `stats-refresh-<YYYYMMDD>T<HHMMSS>Z` (UTC; exactly `^stats-refresh-\d{8}T\d{6}Z$`) |
| Title | `stats: refresh snapshot to <sha7>` |
| Body | contains a line `Refs #392`; no `Closes`, `Fixes` or `Resolves` reference |
| Base | `main` |
| Changed files | exactly `wiki/statistics.html`, with files-API status `modified` |

Any mismatch fails the check; the branch form does not fall back to the
numbered rules, so a hand-made branch of that form is refused too. Only
[`tools/wiki/refresh_statistics.py`](https://github.com/amichai-bd/nand2mario/blob/main/tools/wiki/refresh_statistics.py)
opens such PRs; it is non-draft, waits for `PR policy`, merges with the exact
head pinned, and closes its PR on any failure. Its acceptance is the
[policy tests](https://github.com/amichai-bd/nand2mario/blob/main/tools/ci/tests/test_pr_policy.py)
and the [script tests](https://github.com/amichai-bd/nand2mario/blob/main/tools/wiki/test_refresh_statistics.py).
No other automated class exists, and this one authorizes no other file.

## External CI fallback

The [mandatory rule](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md#verification-and-safety)
authorizes equivalent local execution of the remaining hosted checks, `PR policy`
and the `Pages` build, when their hosted execution is externally blocked. Real
failures and missing scoped evidence remain blockers. Follow the
[skill procedure](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/agent-flow/references/external-ci.md)
for evidence, exact-head merge, restoration and honest deployment status. This
standing authorization needs no repeated per-PR approval.
