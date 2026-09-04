# Scenarios

Good: Drive divider edge cases, predict timer events independently, assert local
timing, and show a seeded fault fails for the expected mismatch.

Bad: Copy DUT logic into the scoreboard or call a waveform-only run a passing
test.

Not a trigger: Define undocumented CPU behavior or write synthesizable RTL only.
