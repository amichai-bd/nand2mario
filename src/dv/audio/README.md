# Audio and serial service checks

Contract: [MAS_audio](../../../wiki/src/rtl/audio/MAS_audio.md) and
[MAS_serial](../../../wiki/src/rtl/serial/MAS_serial.md).

`audio-service` composes the actual memory decoder, CPU port, Intel-backed
stores, serial owner and audio gateway, selecting owners exactly as the
[v0.5 system](../../../wiki/src/rtl/system/MAS_system.md) does. It issues real
prepared and committed CPU accesses and fails on any `contract_fault`, so it
proves that `FF01`-`FF02`, `FF10`-`FF26` and `FF30`-`FF3F` are served instead
of faulting.

It reads every address from `FF10` through `FF26` against a literal restatement
of the pinned read-back masks, writes `00` and then `FF` to each and re-reads,
proving the powered-off APU ignores register writes. It reads all 16 wave bytes
as the generated RAM fill, then writes and reads back two full 16-byte patterns.
The serial cases write and read SB and both SC bit patterns.

`audio-mask-fault` forces the actual `NR52` read route to `71`; the intended
mismatch must report expected `70`. `audio-wave-fault` forces the wave write
byte to `00`; the intended mismatch must report the first wave readback.
`audio-service-fault` withholds owner service for the serial destination,
reproducing the original defect: the commit must fire the named
`MEMORY_COMMIT_OWNER_SERVICE` assertion.
