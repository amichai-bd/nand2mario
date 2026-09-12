---
name: update-crewmates
description: Change the nand2mario work caps (active crewmates and open PRs) everywhere they are stated, verify no stale number survives, and log the change. Use when the owner invokes /update-crewmates <crewmates> <open-prs>; do not use to change any other work rule.
---

# Update crewmates

The owner sets two work caps for each root orchestration tree: how many
crewmates may be active at once and how many PRs may be open. Both are stated
as number words in prose, so a change must land in every sentence at once.
This skill owns that list and the proof that nothing stale survives.

"Crewmates" counts every active subagent: authors, reviewers, scouts and nested
agents alike. A reviewer or a scout takes a slot exactly as an author does.

## Invocation

`/update-crewmates <crewmates> <open-prs>`, for example `/update-crewmates 4 2`.
Both numbers are required; repeat the unchanged one. Then run:

```powershell
python .agents/skills/update-crewmates/scripts/update_caps.py <crewmates> <open-prs> --by <who-asked>
```

The script:

1. Rewrites each location below, keeping the number as a word where the prose
   uses words. Each pattern must match exactly once, or it stops before writing.
2. Appends one line to [HISTORY.md](HISTORY.md): date, old to new, who asked.
   The current caps are the last line of that log and the sentences themselves.
3. Scans `AGENTS.md`, `.agents`, `wiki/agents`, `worktrees/README.md` and
   `.claude` for any cap phrase whose number differs from the requested caps and
   fails, naming the file and line. Run with `--check` to scan without writing.

Paste the scan output into the PR, with a word-diff of `AGENTS.md` proving that
only the numbers changed.

## Locations

| File | Statement | Cap |
| --- | --- | --- |
| `AGENTS.md#work` | `at most <n> open PRs` | open PRs |
| `AGENTS.md#work` | `at most <n> active crewmates` | crewmates |
| `AGENTS.md#work` | `has fewer than <n> open.` | open PRs |

Every other sentence about slots, including
`.agents/skills/agent-flow/references/recovery.md`, is written to hold for any
pair of numbers and states none. Keep it that way: prefer "a crewmate slot" or
"when every slot is in use" over restating a number. When a new sentence must
state a cap, add it to `LOCATIONS` in the script and to this table in the same
change. The scan catches a sentence that was added without being listed,
because it matches phrases rather than the table.

## When the numbers differ

The surrounding text must still read correctly for the pair chosen. With more
crewmates than open PRs, each PR's author and an independent reviewer can be
active together; with equal numbers, an author pauses before its reviewer
starts. Reviewer independence, runtime limits and every other sentence of
`AGENTS.md#work` stay as they are; this skill changes numbers only. Raise any
sentence that no longer makes sense for the new pair to root rather than
rewording it here.

## Inventory

To re-check the list by hand:

```powershell
grep -rn -i "open PRs\|crewmate\|active subagent\|crewmate slot" AGENTS.md .agents wiki/agents worktrees/README.md .claude
```

Hits that carry no number (for example "Preserve open PRs") are not caps.
