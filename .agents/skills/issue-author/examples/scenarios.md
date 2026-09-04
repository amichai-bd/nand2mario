# Scenarios

Good: "Detect stale Questa compile libraries" links the build specification,
states the failing command, and ends with checks for the fixed recreation and a
regression.

Use `bug.md` for a failure with recreation evidence, `enhancement.md` for new
observable behavior, and `specification.md` for one missing design contract.
Keep the matching `type:*` label from that template and replace its area and
priority examples with the issue's real labels.

Bad: "Improve simulation" mixes tool setup, RTL changes, and CI work without an
observable goal.

Not a trigger: Open or update a pull request for completed work.
