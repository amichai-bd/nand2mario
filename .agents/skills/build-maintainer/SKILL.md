---
name: build-maintainer
description: Design or maintain nand2mario host build tooling and workdir artifacts. Use for build stages, caching, manifests, tool discovery, and command behavior; do not use for DUT behavior.
---

# Build maintainer

Follow `wiki/tools/n2m/SPEC.md`. Do not claim planned commands work.
Use the [ownership map](../../../wiki/ownership.md) to align tool PRD/SPEC,
`tools/` implementation, tests, and evidence during
[review](../agent-flow/references/review.md#code-spec-and-test-alignment).

1. Keep commands small, deterministic, scriptable, and useful from PowerShell.
2. Put generated files only under `workdir/builds/<tag>/`.
3. Reuse tagged stages only when their content fingerprint matches.
4. Record commit, inputs, tools, seed, commands, status, and artifacts.
5. Test success, failure, stale cache, missing tool, and path-with-spaces cases.

Use [the stage record](templates/stage.md) when defining output. Read
[the scenarios](examples/scenarios.md) for boundaries. Stop when the build
contract or tool license is unknown.
