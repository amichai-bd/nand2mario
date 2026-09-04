---
name: grill-me
description: Resolve material human decisions before a nand2mario issue or implementation starts. Use for ambiguous, costly, or hard-to-reverse choices; skip when the issue and linked specifications already settle the work.
---

# Grill me

Turn an unclear request into a confirmed decision packet. Do not create issues,
edit files, or take external action during the interview.

This repository skill targets GPT-family Codex agents. It is self-contained; do
not delegate to an upstream skill or translate its flow into another agent tool.

## Method

1. Read the repository, linked specifications, and known constraints. Find facts
   with available tools instead of asking the human.
2. Map the remaining decisions and their dependencies. Ask only questions that
   could change scope, architecture, acceptance, risk, cost, or an irreversible
   action.
3. Ask the ready decision frontier in a short round. Each question includes:
   - the decision and why it matters;
   - two or three concrete choices;
   - a recommendation with its main tradeoff.
4. Wait for the answers. Recompute the frontier. Challenge contradictions and
   assumptions with evidence, then ask the next ready round.
5. If a decision needs a prototype, measurement, private input, or permission,
   name that dependency. Do not replace missing evidence with a guess.
6. When no material decision remains, present the packet below. Ask the human to
   confirm or correct it. Do not hand off to implementation before confirmation.

Prefer one to three questions per round. A dependent question waits for a later
round. Do not ask about naming, formatting, or implementation detail unless it
changes an observable result.

## Decision packet

- **Goal:** one observable result.
- **Decisions:** chosen behavior and important rationale.
- **Non-goals:** tempting adjacent work that is excluded.
- **Risks and dependencies:** unresolved evidence, permissions, or inputs.
- **Wiki impact:** pages to create or update as sources of truth.
- **Issue shape:** suggested title, scope, and three to five success criteria.
- **Confirmation:** the human's explicit approval or requested corrections.

The packet informs the wiki and issue. It does not replace them. After approval,
use the repository issue flow to record the work.

## Stop conditions

Stop when the packet is confirmed, the human pauses the interview, or progress
requires evidence or authority that is unavailable. Preserve unresolved items;
do not silently choose for the human.

## Examples

Good: Before choosing a Game Boy-to-VGA frame crossing, inspect the current
clock plan and DE10-Lite memory limits. Ask whether tearing-free output or lower
memory use wins if both cannot be proven together. Recommend a double buffer,
state its block-RAM cost, and wait for confirmation before writing the CDC spec.

Bad: Ask which DE10-Lite FPGA is installed when the board manual already answers
it, present ten unrelated questions at once, assume a single clock domain, and
start editing RTL before the user confirms the tradeoff.

## Provenance

Adapted from Matt Pocock's `grill-me` and `grilling` skills at commit
`3cca18b368ae95cdbdebbff572ccafa662551015`:

- <https://github.com/mattpocock/skills/tree/3cca18b368ae95cdbdebbff572ccafa662551015>
- [Upstream MIT license](LICENSE.upstream.txt)

The decision tree, ready-frontier interview, recommendations, fact-finding, and
confirmation gate were adapted. Repository-specific issue and wiki outputs,
bounded rounds, mutation boundary, stop conditions, and FPGA examples were added.
