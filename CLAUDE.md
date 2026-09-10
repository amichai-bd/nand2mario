# CLAUDE.md

The agent rules for this repository are the same for every agent and live in one
file. Read it now and follow it in full:

@AGENTS.md

## Notes for Claude Code

Skills are authored once under `.agents/skills/<name>/`. The entries under
`.claude/skills/<name>/SKILL.md` exist only so Claude Code can discover them;
each one points at the canonical `.agents/skills/<name>/SKILL.md`, which is the
file to read and follow. Add or change a skill in `.agents/skills/` only; when you add one, add a
matching pointer file here with the same `name` and `description`.

Development happens on Windows. Prefer PowerShell for tooling that expects it,
and keep paths relative to the repository root.
