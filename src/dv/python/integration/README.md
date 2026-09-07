# Independent integration diagnostic

`python-integration` reproduces the public UART request schedule retained for
[#174](https://github.com/amichai-bd/nand2mario/issues/174). It uses the real
UART, CPU, PPU, memory owners and pinned Intel memory model. The
[integration contract](../../../../wiki/src/dv/integration/SPEC.md) owns the
program, complete literal retirement expectations and pixel timing.

The Python test independently encodes requests and drives the UART RX pin.
It observes applied pin values and decodes UART TX replies, including CRC,
sequence and successful status. It checks all fields of the contract's 69
retirement records, 145 bus observations, selected RAM/stack/tile writes, and
both complete 23040-pixel frames. The normative retirement JSON is shared;
the legacy driver and checker are not imported. Bus observations sample the
consumed pre-edge transaction; retirement and pixels sample 1 ns after the edge.
The HDL wrapper supplies only clock, public observation latches and supported
Intel initialization parameters. An explicit plusarg provides the negative proof.

The sequence sends PING, identity reads, LOAD_BEGIN/LOAD_END to adopt the
preinitialized image, paused-state reads, INPUT0 at 150001000 ns, and RUN at
150201000 ns. Requests are scheduled with a 1 ps guard and start on the next
40 ns falling clock boundary. Serial bits last 320 ns; bytes start 3240 ns
apart. Reset deasserts at 320 ns. Execution completes after dot 136280; Python
polls the final bound every microsecond, so the finish may be a few dots later.
The cocotb test has a 210 ms simulation bound and the builder a 600 s wall bound.
No TCP bridge or repeated Tcl `run` calls participate.

Use the [pinned environment](../README.md), then run:

```powershell
workdir/builds/python-dv-env/.venv/Scripts/python.exe tools/build.py sim test python-integration --tag integration-python --json
workdir/builds/python-dv-env/.venv/Scripts/python.exe tools/build.py sim test python-integration --tag integration-python-repeat --json
workdir/builds/python-dv-env/.venv/Scripts/python.exe tools/build.py sim test python-integration-fault --tag integration-python-fault --json
```

The fault target forces the actual DUT's normal-frame shade to 1. The unchanged
checker must report `INTEGRATION_PIXEL frame=1 index=0 expected=0 actual=1` and
the builder must exit 1. This is a failed test, not a cached positive stage.

Each immutable attempt contains transactions JSONL, retirement/bus/pixel CSV,
result XML, initialization and software image files, WLF/VCD of top-level
public signals, simulator logs, and the builder's source/model/runtime hashes.
Compare applied-input traces as well as output traces before attributing a
change to execution control. Buffered output or wave size does not identify an
exact simulator stall point.

## Historical source comparison

The retained legacy diagnostic uses a source union that differs from main.
`stage_snapshot.py` verifies every file in that snapshot's manifest and makes
a temporary source tree under this author's build directory. Only RTL and the
composed `n2m_smoke_system` come from the historical snapshot. Current builder,
Python test, wrapper and software packager remain current. A fingerprinted
`historical-identity.json` records the boundary and exact historical hashes.

```powershell
python src/dv/python/integration/stage_snapshot.py <retained-snapshot> workdir/builds/historical/source
# From the generated source directory, using the same pinned interpreter:
<pinned-python> tools/build.py sim test python-integration --tag positive --json
```

Use a new destination for another staged source version. Do not commit or
maintain that source tree. Compare its source/model and generated initialization
hashes with the retained legacy run before calling it a controlled comparison.
Historical success does not establish current-head acceptance. Current-source
results and historical results must be labeled separately in review evidence.

This diagnostic does not upload/read back the complete ROM, run the product
Client, halt through the final host command, or replace #164/#168 acceptance.
Success narrows the timeout to a dependence on the verification/execution path;
it does not by itself identify a defective Tcl operation, prove all RTL correct,
or justify a testbench migration. Runtime conclusions belong to the PR evidence.
