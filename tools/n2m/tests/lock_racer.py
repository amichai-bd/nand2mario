"""One real process racing for a tag lock; the tests choose its schedule.

Usage: lock_racer.py <root> <tag> [--before-enter <gate>] [--after-read <gate>]
                     [--hold <done>]

The racer enters ``workspace(root, tag)`` and prints one JSON line:
``{"pid": n, "held": bool, "error": message-or-null}``. With ``--after-read``
its first two owner reads each write ``<gate>.read<n>`` and wait until
``<gate>.go<n>`` exists, so a test can make the first read predate another
racer's reclaim and can hold a reclaim that reads a moved lock (a second read)
open while a third racer enters. With ``--before-enter`` it writes
``<gate>.ready`` once started and waits for ``<gate>`` before entering, so a
test can start it into another racer's reclaim rather than into interpreter
startup. With ``--hold`` a racer that took the tag writes ``<done>.held`` and
keeps the tag until ``<done>`` exists. Only the waits are injected; the lock
mechanism under test runs unchanged across processes.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import n2m.records as records


def wait_for(path):
    while not Path(path).exists():
        time.sleep(.005)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("tag")
    parser.add_argument("--before-enter")
    parser.add_argument("--after-read")
    parser.add_argument("--hold")
    args = parser.parse_args()
    if args.after_read:
        real, reads = records.lock_owner, []

        def owner_then_wait(lock):
            owner = real(lock)
            reads.append(lock)
            if len(reads) <= 2:
                Path(f"{args.after_read}.read{len(reads)}").touch()
                wait_for(f"{args.after_read}.go{len(reads)}")
            return owner
        records.lock_owner = owner_then_wait
    result = {"pid": os.getpid(), "held": False, "error": None}
    if args.before_enter:
        Path(args.before_enter + ".ready").touch()
        wait_for(args.before_enter)
    try:
        with records.workspace(args.root, args.tag):
            result["held"] = True
            if args.hold:
                Path(args.hold + ".held").touch()
                wait_for(args.hold)
    except ValueError as error:
        result["error"] = str(error)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
