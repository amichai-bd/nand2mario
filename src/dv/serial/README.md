# Serial checks

Contract: [MAS_serial](../../../wiki/src/rtl/serial/MAS_serial.md).

`serial-registers` drives the actual owner with an independent expectation.
It checks both reset reads before and after reset release, then sweeps all 256
SB bytes, confirming each readback and that SC is untouched. It then sweeps all
256 SC bytes, confirming the read is `{bit7, 000000, bit0} | 7E` from a literal
restatement of the mask, and that SB is untouched. Prepared but uncommitted
writes and a committed read change nothing. Both reset kinds win over a
competing write. The expectations never call product functions.

`serial-register-fault` forces the actual SC read route to `7C`. The intended
mismatch must report the first SC read after reset release with expected `7E`.
`serial-boundary-fault` commits outside `gb_tick` and must fire the named
`SERIAL_COMMIT_BOUNDARY` assertion.

No transfer, shift clock or serial interrupt is modeled here, because the owner
implements none. The composed [audio and serial service
check](../audio/README.md) proves the same registers over the real CPU port.
