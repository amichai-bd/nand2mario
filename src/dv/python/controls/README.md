# Actual board controls

`python-controls-system` instantiates the shared controls/system module used by
`v05_controls_proof`. The fixture supplies specified 25 MHz/25.2 MHz clocks and
qualified reset inputs. The real ADC PLL, installed ADC model, physical producer
and actual system remain in that shared module. Python drives reset, four button
pins and UART. The separate board fit proves its three PLLs and qualified resets. Original ADC sample
files provide 0.625 V and 1.25 V: codes 1024 and 2048, giving mask `08` under the
nominal calibration. These are simulation inputs, not measured hardware facts.

The existing original v0.5 ROM preload and UART adoption establish a valid image.
The core stays paused. Seven literal public MMIO/LED observations check UART
mask isolation, A-button debounce, physical selection, core RESET retention and
A release. The real default ADC 10 ms reset qualifier and 5 ms button debounce are
unchanged. The board clock qualifier remains in the separately fitted shell. The candidate waits 13 ms for startup (subject to the bounded startup measurement) and 6 ms per button transition, with
a 45 ms simulated watchdog and 300-second total wall limit. The 120-second target
remains an unmeasured goal until execution.

The corrupt target arms a background injector before the real A-release update.
It requires mask `08`, a valid off-tick commit and physical selection, then forces
the actual system input to zero for one accepting edge. It releases that input
at the next falling edge before the unchanged Python oracle runs. The expected
`08` physical/effective state and LED mask must fail. An absent injection fails
separately. The raw Python failure remains a failed builder result, retained as
the intended negative evidence.

The explicit `intel-controls` simulation profile compiles the pinned ADC and RAM
models and generates the same 10 MHz ADC PLL. The board target also generates
the system and pixel PLLs for its strict fit.
It composes the existing exact ADC diagnostic profile and three declared frame
RAM collision diagnostics. Other messages remain failures. Original image bytes,
model files, generated clocks, commands and transactions remain build artifacts.

This proof does not execute the game, replace the accepted system input proof,
or satisfy issue #156's measured calibration and physical eight-control checks.
