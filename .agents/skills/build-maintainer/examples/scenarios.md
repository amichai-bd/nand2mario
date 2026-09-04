# Scenarios

Good: Reject a cached simulation stage after a source or tool-version change and
record the new fingerprint and exact command.

Bad: Reuse a tag by directory name alone or write generated output into `src/`.

Not a trigger: Change a CPU instruction or board pin assignment.
