# Native Springtrail reference

Issue [#277](https://github.com/amichai-bd/nand2mario/issues/277) supplies an
executable reference prerequisite for #263. It does not compare a DUT, close
the milestone, replace every-frame acceptance with CRC, or authorize hardware.

Use the existing pinned Core213a12ce93d66b105a113debd9396306066a7cfc and Expat
source manifest, unchanged direct-entry `profile.c` and native build flags.
The Springtrail case uses the untouched Core, public framebuffer/VBlank and
key APIs. It does not apply the legacy observer patch or retirement projection.
Two clean MISS builds in the #263 assessment produced the exact32768-byte
image frozen in `springtrail.json`; both input and artifact records are retained.

`springtrail-short` stops normally after four native normal-frame callbacks;
`springtrail` stops after twelve. Retain the initial LCD-off callback too:
one type1 callback and one type2 LCD-enable callback precede the type0 frames.
Pinned `Core/memory.c:1503-1512` emits the artificial callback because LCD
enable occurs more than4560 dots after the preceding callback. Do not discard artificial frames,
substitute startup pixels or choose expected state from observed DUT output.
The raw callback identity, completed native dot and software mode accompany
each frame. All23040 public RGB pixels map exactly white/AA/55/black to
shade0/1/2/3 and are stored row-major, one byte per pixel, in `frames.shades`.
The checked ledger gives each frame's offset, size, SHA256 and CRC32.
CRC is an additional identity, not a substitute for the complete stored image.

The frozen two input requests are Start+Right129 at137000 dots, then Right1
at207224. Apply through `GB_set_key_state` after the first GB_run return at or
after the requested dot, recording the actual dot and mask. Reject lateness
above24 dots, missing/extra inputs or changed masks. The finite1000000-dot
guard is independent of frame completion. Require title mode0 initially,
playing mode1 finally, the complete callback count and a terminal record.

The public command remains the existing probe, for example:

```powershell
python src/dv/sameboy/probe.py --case springtrail-short --source <pinned-source> --rom <immutable-image> --output workdir/builds/s277/reference
```

Springtrail invocations use the existing300-second supervisor, including
source qualification, compile, native execution, checks and12-second cleanup.
WSL children receive the same absolute execution deadline. Historical legacy
probe bounds do not apply to this case. Measure the complete short harness
before the twelve-frame case. Initial unmeasured forecast is30-60 seconds
per fresh native build; positive/fault aggregate target remains300 seconds.

The explicit frame fault changes the first emitted shade; the input fault
applies a zero key mask; the progress fault exits before the normal-frame
count. The unchanged checker must reject their respective boundaries despite
raw native exit0. Bad ROM size/hash is rejected before Core or tools execute.
Host negatives also cover truncated images, missing/duplicate callbacks and
missing terminal output. These are reference-runner faults, not DUT fault proof.
Legacy fixed-image cases and #263's full milestone criteria remain unchanged.

The initial `s277` native run finished normally in5.932 seconds but its checker
rejected the omitted type2 prefix expectation. That attempt remains FAIL; the
corrected contract retains and requires this callback and its complete image.

The completed matrix at7499303 retained six callbacks for the short case and
fourteen for the twelve-normal-frame case, including both initialization
callbacks. Each native command exited0; the three intended checker failures
returned outer1. Total successful/fault matrix28.176 seconds; the initial
callback-expectation failure adds5.932 seconds separately. Every invocation
met120-second target and300-second hard limit. No milestone runtime is inferred.
Exact commands, tool provenance, output hashes and source qualification are in
[PR279](https://github.com/amichai-bd/nand2mario/pull/279).

The separate `springtrail-settled-short` and `springtrail-settled` cases own the
[#281 input correction](../springtrail/JOYP_SETTLE.md), with four/twelve normal
frames and the same input script. They require `settled_image`, observe sampled
buttons at C019, and compare every frame byte to independently computed scenes.
The fixed callback mapping is three blank images, title, then successive game
updates129 followed by1. The original cases/image and their historical ledgers
remain unchanged; they do not claim this new game-image agreement.
