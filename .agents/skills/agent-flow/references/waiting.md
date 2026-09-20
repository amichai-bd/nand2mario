# Waiting for a long command

A wait that cannot finish looks exactly like patience, and a wait that finishes
early looks exactly like success. Read this before writing a polling loop.

## Matching a process proves less than it looks

```text
until ! pgrep -f "build.py check --tag mytag"; do sleep 10; done
```

`pgrep -f` matches the whole command line of every process on the host. Run that
loop inline, as an agent does, and the waiting shell's own command line is the
text of the loop, so it holds the pattern and matches itself. The condition can
never become true. Nothing reports a fault: no error and no output, only a loop
that spins until something external kills it.

The self-match needs the loop to be the shell's command line, which it is under
`bash -c`. The same loop inside a script file has the command line `bash loop.sh`
and does not match itself. That is no rescue, because any other process holding
the text matches too: an ancestor, a sibling waiting on the same tag, or the
command that wrote the script. A process-pattern wait ends when nothing on the
host mentions the pattern, which is not the question you asked.

## What it has cost

These durations come from one day's session history, not from anything in this
repository, so they are reported observations rather than figures a check can
confirm:

- 1 hour 35 minutes, guarding a step that had already finished
- 2 to 3 hours before its author found the cause
- 1 hour 8 minutes, killed as an orphan, polling a removed worktree
- 7 hours 30 minutes and 2 hours 59 minutes, killed as orphans, still polling
  directories that had been deleted
- 7 minutes waiting for a command that had never started, stopped once noticed
- root's own cleanup check, which reported the number of surviving waiters going
  up rather than down, because the check matched itself

The list is not exhaustive and no complete count exists. More have been found on
this host since, including waiters near twenty hours, by several different agents
and by cleanup rather than by any procedure that looks for them. Treat the trap as
common and its frequency as unknown.

A root status report from the same session called a finished test run still
running after more than a thousand seconds, from the same cause.

## Two forms that work

Wait for a marker the work writes when it finishes:

```text
deadline=$(( $(date +%s) + 1800 ))
until [ -f workdir/wiki/browser/quality-result.json ]; do
  [ "$(date +%s)" -lt "$deadline" ] || { echo "no result after 30 minutes" >&2; exit 1; }
  sleep 10
done
```

Break the self-match with a bracket:

```text
deadline=$(( $(date +%s) + 1800 ))
while pgrep -f "[b]uild.py check" >/dev/null; do
  [ "$(date +%s)" -lt "$deadline" ] || { echo "still running after 30 minutes" >&2; exit 1; }
  sleep 10
done
```

`[b]` is a one-character class. It matches the same literal `b`, so the pattern
still matches the running `build.py check` while the bracketed text itself does
not.

The bracket covers the pattern, not the rest of the command line. A waiter seen on
this host bracketed its pattern and then announced the result with
`echo "closure-trace finished"`, so its own command line held the plain text and it
hung for 5 hours 12 minutes; a second waiter, holding no literal at all, was held
5 hours 8 minutes by matching the first. Announcing what you waited for defeats a
correct bracket. A marker wait carries no pattern for any of this to reach.

## Pick a marker the work writes at the end

"Wait for a result file" is not advice until it names the file. A marker written
when the work starts proves only that it started. `tools/wiki/check.py` writes
`workdir/wiki/browser/result.json` as `{"status": "starting"}` while it parses
arguments, so a loop watching that path returns about two seconds into a
75-second gate and reports success. The same function deletes
`quality-result.json`, `failure.png` and `trace.zip` before the work begins, and
the last script it runs writes `quality-result.json` when the gate passes, so
that file appears only because the work produced it.

Prefer the marker over the bracket. The bracket protects one piece of text, not
the command line that holds it and not any other process, and it still exits at
once, reporting success, for a command that never started. A completion marker
answers the question that was asked, whatever the process table holds.

## Bound the wait

Both forms above carry a deadline and report reaching it as a failure. Give every
wait one. The orphans above were unbounded waits, left polling paths that had been
removed under them. Stopping owned processes remains part of
[cleanup](../../../../worktrees/README.md#clean-up-after-merge).
