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
one type1 callback precedes the type0 frames. Do not discard artificial frames,
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
