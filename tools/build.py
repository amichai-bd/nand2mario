"""Entry point: python tools/build.py --help."""
import sys

# Generated Python caches belong under workdir, never beside source files.
sys.dont_write_bytecode = True
from n2m.test_budget import main

if __name__ == "__main__":
    raise SystemExit(main())
