# Continuous original host play

This test executes the unchanged [original host-play contract](../../../../wiki/tools/host-play/SPEC.md)
through the public product Client. The shared continuous UART `connect` and
`frames` functions drive and receive actual serial pins. No Tcl mailbox, private
game-state injection or behavioral replacement memory participates.

The original software pipeline builds the same host-play ROM. `play()` performs
full upload/readback, explicit UART source selection, complete WRITE_HOST masks,
RUN/HALT, SNAPSHOT and every READ_FRAME chunk. Its existing independent checks
require all five complete images: (64,64,1), (72,64,3), (72,64,1), (64,64,3),
(64,64,1), with all other pixels zero. Epoch2 and increasing frame identity remain
mandatory. The Python wait callback observes only public elapsed dots:200000
initially and150000 for each later stage, totaling800000 requested dots.

The HDL wrapper instantiates the same composed HOST_PLAY system and installed
Intel memories. It supplies the25MHz clock and the four existing actual fault
forces. Python owns reset release at320ns, serial stimulus, bounded observation
and image verdicts. The composed pixel clock remains25.2MHz. The test requires
final host-paused state and epoch2. It rejects an owner fault or more than one
million dots.

Using the [pinned Python environment](../README.md), run:

```powershell
workdir/builds/python-dv-env/.venv/Scripts/python.exe tools/build.py sim test python-host-play --tag python-host-play --json
```

The four negative targets are `python-host-play-frame`, `python-host-play-missing`,
`python-host-play-input` and `python-host-play-release`. They force actual snapshot
data, completion, JOYP buttons or release commit. The original checker must fail
with PLAY_OBJECT_COUNT, PLAY_MISSING_FRAME, or the exact wrong image respectively.
Python test failure and builder exit1 are required; raw simulator exit0 alone is
not success. Expected images are never changed to accommodate a fault.

The one-second simulation and1500-second builder bounds preserve the existing
host-play budgets. The wait callback checks its300-second wall budget whenever
simulation scheduling resumes. A returned serial reply must meet the120-second
wall progress bound. An unresponsive simulator is ultimately bounded by the
builder; these cooperative checks do not interrupt a blocked native simulator.

Artifacts include actual Client requests/replies, applied serial bits, each full
packed/grayscale image, independently recognized object and frame metadata,
wait intervals, failure details, source/model/runtime identities, XML and public
waves. Legacy host-play targets remain distinct. These tests do not close full
v0.5, physical verification or the unresolved finite-Tcl mechanism investigation.
