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

Measured in one day, each agent independently:

- 1 hour 35 minutes, guarding a step that had already finished
- 2 to 3 hours before its author found the cause
- 7 minutes waiting for a command that had never started
- 7 hours 30 minutes and 2 hours 59 minutes, killed as orphans, still polling
  directories that had been deleted
- 1 hour 8 minutes, polling a removed worktree
- root's own cleanup check, which reported the number of surviving waiters going
  up rather than down, because the check matched itself

A root status report from the same session called a finished test run still
running after more than a thousand seconds, from the same cause.

## Two forms that work

Read the result file:

```text
until [ -f workdir/wiki/browser/result.json ]; do sleep 10; done
```

Break the self-match with a bracket:

```text
until ! pgrep -f "[b]uild.py check" >/dev/null; do sleep 10; done
```

Prefer the result file. The bracket form fixes only the self-match. It still
exits at once, reporting success, for a command that never started, which is the
7-minute case above. A result file exists because the work produced it, so its
absence means the work is not done, whatever the process table holds.

## Bound the wait

Give every wait an iteration cap or a deadline, and treat reaching it as a
failure to report rather than a reason to keep waiting. An unbounded waiter
outlives its purpose: six were killed as orphans on the day above, still polling
paths that had been removed under them. Stopping owned processes remains part of
[cleanup](../../../../worktrees/README.md#clean-up-after-merge).
