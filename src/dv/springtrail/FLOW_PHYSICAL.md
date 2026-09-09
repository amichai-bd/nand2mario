# Bounded interaction flow preparation

This extends the existing physical driver pattern for #262. It is not yet a
physical result or a claim that Windows UART latency meets these windows.
The owning game contract supplies the approved one-frame prepared-image lag.
The author must freeze the exact source-derived LCD anchor and `flow_frames.image`
with the assembled game before execution; no value is selected from observed pixels.

`flow_physical_reference.py` maps planned source frame n>=1 to the independent
Game state after n-1 logical updates. Public INPUT application dots determine
the sampled masks at fixed70224-dot periods. Reject VBlank input transitions,
wrong epoch/sequence and completion outside the independently known row143.
The planned frame chooses expected state; metadata only confirms identity.

`flow_physical_driver.py` uses ordinary RUN/HALT, never STEP-as-time. A mask for
logical update n must be applied while paused in visible frame n-1, between
offset4096 and60000. Sleep only paces commands. Actual HALT/applied dots prove
the window; six bounded approaches cannot extend it. Overshoot fails rather
than moving the expected schedule to a favorable time.

Before a full route, the `feasibility` mode exercises eight consecutive such
windows with INPUT0, then checks a title image and safe completion. It uses the
same package/Client/driver path and does not start gameplay. This short timing
diagnostic is not successful-level evidence. Actual FTDI/Windows latency is
unmeasured here: if a window is missed, preserve the failed record. Do not retry
the same full route or claim the360-update model route proves UART feasibility.
A separately frozen robust waypoint/held-edge plan would then be needed.

The candidate success flow retains every world-state checkpoint of the
canonical360-update alive goal/score2 route. Each A pulse is held for10 updates,
subtracting nine from the following Right+B interval; initial Start+Right+B is
held for nine updates. Only previous-button history changes. Host checks compare
every state field other than that explicit history for all360/188 updates.
Longer holds do not establish absolute-window feasibility; the same diagnostic
and overshoot failure remain required. The success flow then checks win retry,
pause with held Start, held-A resume without a
queued jump, Select/Start restart priority, Select ignored during play, and
another Select restart during map reconstruction. The final16 right-run updates
remain at camera0. Logical UpdateGame never freezes for reconstruction; the
hidden map copies two columns per publication for16 publications. Full images
before/after this boundary must agree with the same independent game state.
There are394 planned updates and21 selected full-frame checks. The separate
death/retry flow has188 planned updates and four checks, including the collected
item, gap fall and complete reset state. Capturing the final prepared image
requires two further ordinary sample boundaries; those tail updates are modeled,
not omitted from elapsed time. No every-frame milestone proof is claimed.

The caller owns fresh immutable ROM build/full load/readback, qualified board
fit/SOF and verified device/electrical setup, canonical mutex, durable session,
fresh output folder and existing300-second whole supervisor with12-second cleanup.
No reprogramming is implied. Prior certain sequence, build, paused dots and exact
surviving snapshot identity must match before a warm load derives epoch+2.
Identity failure sends no cleanup controls. After verified preflight, known
failures attempt HALT/INPUT0; uncertain completion forbids further traffic.
Record packet journals, actual applied windows, all packed snapshots and final
PAUSED/UART/input0/certainty. No hardware traffic was used to prepare these files.
