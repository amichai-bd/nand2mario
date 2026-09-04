---
name: wiki-spec-writer
description: Create or revise concise nand2mario specifications and design decisions. Use for normative wiki behavior; do not use for work history, logs, or unsupported design choices.
---

# Wiki spec writer

Make one page the source of truth for one contract or decision.

1. Name scope, terms, inputs, outputs, state, timing, reset, and error behavior.
2. Use observable rules with units, bit order, clock domain, and edge cases.
3. Separate requirements from rationale, planned behavior, and open questions.
4. Link primary sources and related contracts. Do not copy issue history.
5. Check links and source/test alignment using the
   [review guide](../agent-flow/references/review.md).

Start from [the spec template](templates/spec.md). Read
[the scenarios](examples/scenarios.md) when deciding whether content is
normative. Stop when a product decision or authoritative source is missing.
