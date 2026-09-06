# Selected SM83 CPU vectors

This is a bounded fixture for [CPU #118](https://github.com/amichai-bd/nand2mario/issues/118),
using the [baseline's reviewed source](../../../../wiki/src/dv/baseline/SPEC.md#singlestep-vectors).
It does not deliver the full adapter tracked by #101.

The upstream data is MIT licensed; retain [LICENSE](LICENSE). [manifest.json](manifest.json)
records the immutable source revision, archive digest, every source-file digest,
original case name/index and selection. The archive is retained in ignored build
research storage. No upstream HDL or commercial program is imported.

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
python src/dv/cpu/generate_vectors.py <retained-archive.zip> --check
```

Omit `--check` only when intentionally regenerating this source fixture. The
generator rejects any archive whose digest differs. It does not fetch mutable
content or discover another version.

The 1,024-bit packet is an original test representation. Byte registers occupy
bits 0–63 in A/F/B/C/D/E/H/L order, SP occupies 64–79 and PC 80–95; final values
repeat at bit 96. RAM counts occupy bits 192–199, cycle count 200–203, instruction
length 204–205, opcode identity 206–214 and source index 215–224. Eight 24-bit
address/byte slots each start at bits 225 and 417 for initial/final RAM. Six
28-bit cycle slots start at 609: address, byte, two-bit idle/read/write kind,
address-valid and data-valid. Unused bits are zero. The assignments in
`vectors.svh` are separate from the testbench array declaration.
