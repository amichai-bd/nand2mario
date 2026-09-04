---
name: grill-me
description: Run a human-alignment interview before nand2mario work. Use only when the user invokes grill-me or $grill-me; do not invoke it for ordinary ambiguity.
---

# Grill me

Turn an unclear request into a confirmed decision packet. Do not edit files,
create issues, or take external action during the interview.

1. Inspect repository facts before asking questions.
2. Ask one to three ready decisions that can change scope, behavior, risk, cost,
   or an irreversible action.
3. Give concrete choices and a recommendation with its tradeoff.
4. Wait, then recompute the remaining decisions.
5. Challenge conflicts with evidence. Do not guess past missing facts.
6. Fill [the decision packet](templates/decision-packet.md) and ask for explicit
   confirmation before handoff.

Read [the scenarios](examples/scenarios.md) when deciding what to ask. Stop when
the packet is confirmed, paused, or blocked by missing evidence or authority.

## Provenance

Adapted from Matt Pocock's `grill-me` and `grilling` skills at commit
`3cca18b368ae95cdbdebbff572ccafa662551015`. See
[the upstream MIT license](LICENSE.upstream.txt).
