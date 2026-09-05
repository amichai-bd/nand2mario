# Contract name

Use the [ownership map](../../../../wiki/ownership.md) to choose a tool PRD/SPEC
or RTL MAS. A PRD owns purpose, scope, and acceptance links; its SPEC owns detailed
behavior and design. An RTL MAS owns its module contracts and microarchitecture.
Use only applicable sections and link shared requirements instead of copying.

## Scope

State what this page governs and excludes.

## Terms

Define exact names, units, widths, and domains.

## Contract

State observable behavior, interfaces, timing, reset, and errors.

## Edge cases

List boundary and conflicting events in priority order.

## Verification

Link owning `src/` or `tools/` implementation, tests proving the rules, and
retained evidence. Mark planned behavior and link its open implementation issue.

## References

Link primary sources and related repository contracts.
