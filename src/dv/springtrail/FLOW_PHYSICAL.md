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
The public paused dot chooses a source frame inside the declared interval;
metadata only confirms identity. Pixels never select expected state.

`flow_physical_driver.py` uses ordinary RUN/HALT, never STEP-as-time. A mask for
logical update n must be applied while paused in visible frame n-1, between
offset4096 and60000. Sleep only paces commands. Actual HALT/applied dots prove
the window; six bounded approaches cannot extend its declared end. RUN response
wall time is subtracted from requested sleep. RUN/HALT durations, sleep and actual
dot advance are retained. Movement input windows remain exact; overshoot fails.

Before a full route, the `feasibility` mode exercises eight consecutive such
windows with INPUT0, then checks a title image and safe completion. It uses the
same package/Client/driver path and does not start gameplay. This short timing
diagnostic is not successful-level evidence. Actual FTDI/Windows latency is
measured only by its retained result. A passing probe does not guarantee later
latency. Preserve every failed run separately; do not reroll it.

The candidate success flow retains every world-state checkpoint of the
canonical360-update alive goal/score2 route. Each A pulse is held for10 updates,
subtracting nine from the following Right+B interval; initial Start+Right+B is
held for nine updates. Only previous-button history changes. Host checks compare
every state field other than that explicit history for all360/188 updates.
Longer holds do not establish absolute-window feasibility; the same diagnostic
and overshoot failure remain required. The movement prefix has360 updates and
six selected images. After winning, neutral remains held until a checked WON
image with score2. Its capture permits visible frames362 through370. No retry
Start is sent before this check. The death prefix stops at187 updates, holds its
last mask in RETRY, and checks score1 in visible frames189 through197 before
retry. Earlier selected captures retain their exact windows.

The success tail uses these fixed masks in order:128,0,128,16,144,0,128,192,64,0,64.
Each is applied while paused, then captured four through eight visible frames
later. They cover win retry, held Start pause, A held across resume without a
queued jump, another pause, Select priority restart, held Select and a new Select
edge ignored during play. The death tail uses only128 to retry. Every selected
image is checked against the same independent model driven by all actual INPUT
dots, including the publication lag and extra elapsed updates. Pause additionally
checks frozen timer/enemy/player; restart checks position24,112 and zero score,
and ignored Select checks timer progress. There are17 success images and four
death/retry images. Rules, ROM, clocks and display timing are unchanged.

Exact mid-rebuild repeated reset and complete reset bytes remain covered by the
existing component/composed proofs. This physical tail does not claim that exact
boundary or an every-frame milestone. The earlier failed exact-tail run remains
FAIL; widening only the declared stable captures is a changed mechanism.

The caller owns fresh immutable ROM build/full load/readback, qualified board
fit/SOF and verified device/electrical setup, canonical mutex, durable session,
fresh output folder and existing300-second whole supervisor with12-second cleanup.
No reprogramming is implied. Prior certain sequence, build, paused dots and exact
surviving snapshot identity must match before a warm load derives epoch+2.
Read SNAPSHOT_VALID/EPOCH/SEQ and READ_FRAME against the prior captured hash;
do not issue a new SNAPSHOT during preflight, since later RUN may have advanced
the producer. Recovery from a certain failed run binds its actual acknowledged
HALT/INPUT0 and its last acquired snapshot, not an inferred newer image.
Identity failure sends no cleanup controls. After verified preflight, known
failures attempt HALT/INPUT0; uncertain completion forbids further traffic.
Record packet journals, actual applied windows, all packed snapshots and final
PAUSED/UART/input0/certainty. No hardware traffic was used to prepare these files.
