# Host commands

Implemented by [tools/n2m/host](../../../../tools/n2m/host/client.py), dispatched
through `python tools/build.py host`. The [PRD](PRD.md) owns requirements.
The [interface MAS](../../../src/rtl/interfaces/MAS_interfaces.md) and generated
exports own all wire, register, profile and frame values.

The focused `python tools/stackdrop_player.py` entrypoint uses this same Client,
package validator and durable session for the
[frozen Stackdrop comparison](../../../src/sw/stackdrop/SPEC.md#pixel-player-comparison).
Its explicit private setup/state files bind the verified device, board build,
prior paused dots, frame identity and durable sequence. Run baseline once, then
strategy once; an attempted or uncertain run cannot be silently restarted.
Each invocation uses the existing300-second supervisor and canonical machine
lock. Pixel observations and packet journals are retained under its build tag.

## Commands

Every operation accepts `--tag`, `--json` and the doctor's `--uart-port`,
`--uart-vid`, `--uart-pid`, `--uart-identity` selectors. Selectors combine; exactly
one healthy Windows PnP serial device must match. No selection fails. OS identity
is not device authentication or proof of correct wiring.

| Command | Result |
|---|---|
| `host status` | ABI/build identity and single-word state, image-valid, profile and input registers. No incoherent live split counters. |
| `host load --package <result.json>` | Validated immutable software attempt, load begin/write/end, complete byte-for-byte readback, valid/paused/profile checks. Does not run the ROM. |
| `host reset` | Generated core RESET, acknowledged after initialization. |
| `host run` | Resume through generated RUN. |
| `host halt` | Pause through HALT; return completed dots. |
| `host step --dots <budget>` | One instruction with generated budget bounds; STEP_LIMIT is a known failure with consumed time retained. |
| `host run-dots --dots <count>` | Exact bounded real-dot execution; return completed dot, executed count and COUNT/STOPPED reason. |
| `host input --mask <integer>` | Replace the complete active-high eight-button mask, preserving simultaneous/opposite states. Decimal or prefixed hexadecimal is accepted. |
| `host write --address <integer> --value <integer>` | Write the generated INPUT mask or INPUT_SOURCE selector; reject read-only/unknown addresses and reserved value bits before opening the port. |
| `host snapshot` | One SNAPSHOT followed by all READ_FRAME chunks; retain metadata and packed shades. No new snapshot during readback. |
| `host crc-proof --expected-build-id <32hex>` | Fixed bad-CRC PING diagnostic on an already certain, reviewed endpoint. Requires the physical verification workflow below. |

`Client.write_host(address, value)` uses the same whitelist.
`Client.select_input_source(source)` selects UART or PHYSICAL through that write.
Existing `Client.read_host` reads host, physical, source and effective observations;
legacy status/INPUT retain their original host-mask meaning. See the
[shared input owner](../../../src/rtl/input/MAS_input.md) for reset and authority.

Before any operation the host checks PING and host ABI, then records the stable
128-bit build ID. It sends no product operation after an ABI mismatch. The build
ID is evidence, not authentication. An all-zero ID fails before any product
command. The shared contract's unidentified simulation-fixture exception is
not exposed by the physical host CLI.

Load accepts a successful immutable
`workdir/builds/<tag>/sw/build/<target>/runs/<attempt>/result.json`, not a loose
ROM or mutable stage result. Validate attempt/profile, current interface input
hashes and every inventoried artifact within that attempt. Read the image once,
check its hash, exact size and strict owned header/checksums using the packager
validator, then keep immutable bytes for transmission and full comparison.
No expected byte values are logged on mismatch. Each write leaves space for its
generated offset record; every byte is read back after LOAD_END before success.

## Transport and recovery

Discovery reuses the doctor without running its licensed probes. The optional
[pinned serial backend](../../../../tools/n2m/host/THIRD_PARTY.md) opens only the
selected OS port, configured to the generated baud and 8N1 without flow control.
DTR/RTS are set inactive before open; driver-level glitches cannot be ruled out,
so verified wiring and the physical workflow still apply.

The serial device is configured once with nonblocking reads. A transport wrapper
waits for received bytes with a monotonic deadline and sleeps at most one
millisecond between empty reads. Client timeout updates change that local wait,
not the device configuration. This avoids pyserial 3.5 on Windows reapplying
line settings while a packet is transmitting. Packet writes remain whole and
unpadded; there is no inter-byte pacing, flush loop or automatic replay.

Only one request is outstanding. Replies must match generated version, response
kind, sequence, command, status and exact payload shape/length, with valid COBS
and CRC. Empty delimiters are ignored within a bounded overall response timeout.
Partial writes, timeout, malformed or mismatched replies make completion
uncertain. The host stops immediately without retry, reset, reload or another
request. A valid endpoint error is a known failure, not an uncertain reply.

Each selected PnP identity has a repository-shared lock and sequence journal in
ignored `workdir/host-sessions/`, shared across build tags and linked worktrees.
Reserve the next modulo-width sequence and mark pending before transmission;
clear pending only after a valid reply. This retains uncertainty after crashes
or separate CLI invocations. A subsequent command fails before opening while
pending. A stale lock requires confirming its recorded process has stopped;
commands never delete it automatically.

`--endpoint-restarted` is an explicit operator statement that a separately
completed endpoint global reset ended the uncertain session. It clears pending
under the exclusive lock while preserving the increasing sequence. It never
sends reset or replays the previous request. Core RESET does not meet this
condition because it preserves the endpoint retry cache. An immediate retry
within an uninterrupted session is not exposed by this initial host UI.

## Evidence and tests

The CRC proof requires a matching reviewed wire build ID, PAUSED state, UART
source and zero requested/effective input. It rejects `--endpoint-restarted`.
After the prerequisites, it reserves a token and sends an empty PING with one
CRC bit flipped before COBS encoding. Any received byte in the generated
two-second response window fails. A fresh-token normal PING must return ABI1;
subsequent state and stable paused dot/retirement reads must match the baseline.
The diagnostic keeps its durable session pending through all recovery reads and
clears it only after the entire proof succeeds. Failures stop without retry or
state-changing commands. Ordinary Client timeout handling is unchanged.
Run physical proof under the existing 60-second whole-process supervisor,
including its standard cleanup reserve, with verified setup and exclusive access.
This observes silence and recovery, not an internal discard counter or monitor
output; the remaining [board criteria](https://github.com/amichai-bd/nand2mario/issues/28)
remain separate.

Every invocation is fresh, never cached. Unique attempt artifacts live under
`workdir/builds/<tag>/host/<action>/<attempt>/`: discovery, device identity,
transaction journal, result and optional `frame.2bpp`. Journals contain command,
sequence, byte length/hash, response status and decoded non-ROM metadata, never
raw ROM request/readback bytes. Snapshot shades remain ignored private artifacts.
The builder retains commit/dirty fingerprint, requested command and artifact
hashes; failures retain their reason and transaction prefix. Build and device
paths/identities remain local and must not be pasted into public documentation.

[Fake endpoint tests](../../../../tools/n2m/tests/test_host.py) drive encoded
packets, verify all load/readback chunks including the final byte, all input
masks, control transitions, immutable snapshot chunks, malformed replies,
uncertain persistence and device failures before open. They run through
`python tools/build.py check --tag <tag> --json`. Physical evidence is separate
and is not claimed by these tests.
