# Waiting for a long command

A wait that cannot finish looks exactly like patience. Read this before writing
a polling loop.

## The loop that matches itself

```text
until ! pgrep -f "build.py check --tag mytag"; do sleep 10; done
```

`pgrep -f` matches whole command lines, and the waiting shell's own command line
contains the pattern. The loop matches itself, so its condition can never become
true. Nothing reports a fault: there is no error and no output, only a loop that
spins until something external kills it.

## What it has cost

These durations come from one day's session history, not from anything in this
repository, so they are reported observations rather than figures a check can
confirm:

- 1 hour 35 minutes, guarding a step that had already finished
- 2 to 3 hours before its author found the cause
- 1 hour 8 minutes, polling a removed worktree
- 7 hours 30 minutes and 2 hours 59 minutes, killed as orphans, still polling
  directories that had been deleted
- 7 minutes waiting for a command that had never started, stopped once noticed
- root's own cleanup check, which reported the number of surviving waiters going
  up rather than down, because the check matched itself

That is seven instances of the trap in one day. Six waiting shells were killed as
orphans that day, three of them in the list above. The two counts are different
sets: the 7-minute wait was stopped soon after it started, so it belongs only to
the first.

A root status report from the same session called a finished test run still
running after more than a thousand seconds, from the same cause.

## Two forms that work

Read the result file:

```text
deadline=$((SECONDS + 1800))
until [ -f workdir/wiki/browser/result.json ]; do
  [ "$SECONDS" -lt "$deadline" ] || { echo "no result after 30 minutes" >&2; exit 1; }
  sleep 10
done
```

Break the self-match with a bracket:

```text
deadline=$((SECONDS + 1800))
while pgrep -f "[b]uild.py check" >/dev/null; do
  [ "$SECONDS" -lt "$deadline" ] || { echo "still running after 30 minutes" >&2; exit 1; }
  sleep 10
done
```

`[b]` is a one-character class. It matches the same literal `b`, so the pattern
still matches the running `build.py check`, while this shell's own command line
holds the brackets and does not match.

Prefer the result file. The bracket form fixes only the self-match. It still
exits at once, reporting success, for a command that never started, and it still
matches an ancestor whose command line quotes the unbracketed pattern, which is
how the first run of these two examples hung. A result file exists because the
work produced it, so its absence means the work is not done, whatever the process
table holds.

## Bound the wait

Both forms above carry a deadline and report reaching it as a failure. Give every
wait one. The orphans counted above were unbounded waits, left polling paths that
had been removed under them. Stopping owned processes remains part of
[cleanup](../../../../worktrees/README.md#clean-up-after-merge).
