"""Build pinned Icarus from source on Linux/WSL; no Python packages needed."""
import json
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[2]
    if sys.platform != "linux":
        raise SystemExit("Run this script in Linux or WSL; see wiki/tools/n2m/SPEC.md#bootstrap")
    pin = json.loads((root / "tools/n2m/dependencies.json").read_text())["iverilog"]
    source = root / "workdir/tools/iverilog-source"
    prefix = root / "workdir/tools/iverilog"
    log = root / "workdir/logs/iverilog-bootstrap.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    source.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as output:
        def run(argv, cwd=root):
            output.write(json.dumps({"argv": argv, "cwd": str(cwd)}) + "\n")
            output.flush()
            subprocess.run(argv, cwd=cwd, stdout=output, stderr=subprocess.STDOUT, check=True)
        if not source.exists():
            run(["git", "clone", "--no-checkout", pin["url"], str(source)])
        run(["git", "fetch", "origin", pin["commit"]], source)
        run(["git", "checkout", "--detach", pin["commit"]], source)
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True).strip():
            raise SystemExit(f"External source has local changes: {source}")
        run(["sh", "autoconf.sh"], source)
        run(["./configure", f"--prefix={prefix}"], source)
        run(["make", "-j2"], source)
        run(["make", "install"], source)
        run([str(prefix / "bin/iverilog"), "-V"])
        run([str(prefix / "bin/vvp"), "-V"])
    print(f"Installed {pin['commit']} under {prefix}; log: {log}")


if __name__ == "__main__":
    main()
