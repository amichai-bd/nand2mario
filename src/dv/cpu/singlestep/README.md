# Selected SM83 CPU vectors

This bounded adapter uses the delivered [CPU boundary](../../../../wiki/src/rtl/cpu/MAS.md),
using the [baseline's reviewed source](../../../../wiki/src/dv/baseline/SPEC.md#singlestep-vectors).
The adapter scope is [#101](https://github.com/amichai-bd/nand2mario/issues/101).

The upstream data is MIT licensed; retain [LICENSE](LICENSE). [manifest.json](manifest.json)
records the immutable source revision, archive digest, every source-file digest,
original case name/index and selection. The archive is retained in ignored build
cache at `workdir/cache/singlestep/`. No upstream HDL or commercial program is imported.

Selection takes the first source case for each of the 16 initial F high-nibble
values in every opcode file. All 500 files supply every flag value: 8,000 selected
cases, not all 500,000 upstream vectors. The composed CPU target checks 7,968
cases covering 498 forms. The 32 upstream STOP/HALT cases are explicitly skipped;
their power and timing models need the independent directed CPU tests. Upstream
IME/IE/EI expectations are excluded as documented upstream. The isolated test
starts with IME clear and checks simple EI/DI/RETI effects separately.

`tb_cpu_vectors` loads arbitrary flat-RAM/register state only in its simulation
wrapper. The product has no register-write test port. Expected registers and RAM
come from upstream, never DUT state or assembler encoding data. Every committed
write must match the expected address/data cycle, which also checks the write
footprint outside the listed final RAM. Idle bus addresses are not treated as
an established physical IDU model. The fixture checks the final extra opcode
fetch required by the documented overlap pipeline; its T4 placement is our
separately sourced digital contract, not upstream T-edge evidence.

Reproduce the checked-in fixture using the exact archive recorded in the manifest:

```text
python src/dv/cpu/generate_vectors.py --fetch --check
python src/dv/cpu/generate_vectors.py <retained-archive.zip> --check
```

Omit `--check` only when intentionally regenerating this source fixture. The
generator rejects any archive whose digest differs. It does not fetch mutable
content or discover another version. `--fetch` uses only the recorded immutable
URL, rehashes cached content, and publishes downloaded bytes only after digest
verification. It limits size to 256 MiB and checks elapsed time between reads;
the 60-second socket timeout can extend the 180-second elapsed threshold.

The 1,024-bit packet is an original test representation. Byte registers occupy
bits 0–63 in A/F/B/C/D/E/H/L order, SP occupies 64–79 and PC 80–95; final values
repeat at bit 96. RAM counts occupy bits 192–199, cycle count 200–203, instruction
length 204–205, opcode identity 206–214 and source index 215–224. Eight 24-bit
address/byte slots each start at bits 225 and 417 for initial/final RAM. Six
28-bit cycle slots start at 609: address, byte, two-bit idle/read/write kind,
address-valid and data-valid. Unused bits are zero. The assignments in
`vectors.svh` are separate from the testbench array declaration.

The shared builder targets are `cpu-vectors`, `cpu-vectors-state-fault`,
`cpu-vectors-expected-fault` and `cpu-vectors-missing`. The first checks the
selected corpus; the negatives respectively change actual DUT A, expected A,
and suppress the public completion. Expectations remain unchanged in the DUT
fault. The expected-state fault changes only the oracle byte for case zero.

Artifacts include original names/source indices in `vector-identities.csv`,
full expected/actual retirement records in `vector-retirement.csv` and M-cycle
observations in `vector-bus.csv`. State mismatches name the first differing
record field and byte. Log context records the immutable pin, digital model,
exclusions and `seed=none`: selection is deterministic. Public wave capture
covers the first 32 executed cases, including all three negative cases; it is
not a waveform record of the entire corpus. The generator source report records
archive and generated-file hashes. Retain it with the builder run records.
