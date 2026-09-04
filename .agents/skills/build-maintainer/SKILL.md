---
name: build-maintainer
description: Design or maintain nand2mario host build tooling and workdir artifacts. Use for build stages, caching, manifests, tool discovery, and command behavior; do not use for DUT behavior.
---

# Build maintainer

Follow `wiki/tools/build-system.md`. Do not claim planned commands work.

1. Keep commands small, deterministic, scriptable, and useful from PowerShell.
2. Put generated files only under `workdir/builds/<tag>/`.
3. Reuse tagged stages only when their content fingerprint matches.
4. Record commit, inputs, tools, seed, commands, status, and artifacts.
5. Test success, failure, stale cache, missing tool, and path-with-spaces cases.

Use [the stage record](templates/stage.md) when defining output. Read
[the scenarios](examples/scenarios.md) for boundaries. Stop when the build
contract or tool license is unknown.
