---
name: unslop
description: Edit nand2mario repository prose to remove filler and stock AI phrasing while preserving exact technical meaning. Use for issues, PRs, wiki pages, review comments, commit messages, and user-facing status; do not use for code, logs, test data, generated artifacts, or quoted text.
---

# Unslop

Make project prose direct, natural, concise, and exact. This skill is for
GPT-family agents and is tuned for GPT-5.6 Sol.

## Method

1. Identify the audience, purpose, required structure, and source evidence.
2. Preserve every fact, decision, constraint, caveat, path, command, citation,
   number, status, and statement of uncertainty.
3. State the result, evidence, or decision first.
4. Remove content that does no work:
   - generic openings, reassurance, praise, and sign-offs;
   - repeated summaries and conclusions;
   - meta narration about writing or organizing the answer;
   - empty intensifiers, vague qualifiers, and stock transitions;
   - rhetorical questions and invented quotations;
   - contrast frames that introduce an alternative nobody asked about;
   - excessive headings, nested lists, and labels for simple prose.
5. Prefer familiar words, precise verbs, active voice, and short sentences. Keep
   established Game Boy, RTL, DV, FPGA, and tool terms when they are exact.
6. Compare the revision with the source. Restore anything whose removal changes
   meaning or weakens evidence.

Do not apply a word blacklist mechanically or invent a house voice. Preserve
required issue headings, PR closing references, checkboxes, Markdown links, and
code spans. Make no change when the source is already clear.

## Output

Return the revised prose. Add a short note only when a material ambiguity,
conflict, or unsupported claim needs the author's decision.

## Examples

Bad: "It is important to note that this robust change leverages a comprehensive
approach to successfully improve UART reliability."

Good: "The UART test passed 10,000 frames with no checksum errors."

No-op: "TimeQuest reports 4.2 ns setup slack for the 50 MHz clock."

## Design references

- [OpenAI GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6#prompting-best-practices): keep prompts lean, state each instruction once, lead with required content, and remove repetition before evidence.
- [OpenAI model writing guidance](https://developers.openai.com/api/docs/guides/latest-model#personality-and-writing-style): use plain language, direct statements, and only as much structure as comprehension needs.
