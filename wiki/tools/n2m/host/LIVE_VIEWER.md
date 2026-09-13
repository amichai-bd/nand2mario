# Live FPGA viewer

The viewer serves actual160x144 pixels of the software image already loaded on
the board. It never loads, resets or programs that image. A static image can be
fresh: capture and source-frame sequence, not visual change, establish freshness.
The [host command contract](SPEC.md) owns UART/session/snapshot semantics.

## Access

The local server binds only127.0.0.1. Its only routes are GET `/`, `/status.json`
and `/frame.png`, plus POST `/input`, all requiring HTTP Basic authentication.
The POST accepts only a named Game Boy button and queues a fixed134ms tap. It
requires JSON (at most64 bytes), `X-Viewer-Input: tap`, and exact Origin equality
with the explicit `--input-origin https://<public-host>` setting. Forwarded Host
is never an authority. No CORS permission is returned. There are no arbitrary
UART, configuration, upload or file routes. Responses disable
caching, framing and cross-origin access. Credentials are randomly generated,
high entropy and retained only in an operator-private file; never put them in
URLs, logs, source or PR text. The approved temporary Cloudflare Quick Tunnel
provides HTTPS. Pin its official portable release/checksum in local workdir;
no account, router/firewall change or global installation is required.

## Capture and lifecycle

One worker owns the canonical durable UART session and machine lock1357311510.
Fresh doctor, selected healthy device, wiring/voltage provenance and reviewed
ABI/build identity must precede traffic. Require a valid existing image, UART
input authority and effective input0. If paused, the authorized worker resumes
it with input0. The viewer itself never supplies Start or gameplay input. Explicit local operator
and authenticated phone requests use the same bounded queue below. Every capture is one
SNAPSHOT followed by all5760 READ_FRAME bytes, without another capture in between.
The core stays RUNNING throughout captures. Native PNG bytes come only from
those actual packed shades using the existing decoder, not a host model.

A completed capture atomically replaces an in-memory image/status pair. Show
sequence, source completion dot, receive timestamp and measured latency. LIVE
requires a recent successful capture and increasing source sequence/dot within
the same reset epoch; duplicate/stopped source marks STALE, errors mark ERROR.
The page must age to STALE even if polling or the capture process stops.
Failed captures never refresh the last-success timestamp. No application retry
follows protocol uncertainty. One certain rejected capture may be retried on the
next scheduled interval; a second consecutive failure ends the worker.

The local operator chooses a finite session duration and can stop it by a local
stop file or console interrupt. Neither mechanism is remotely exposed. A normal
exit halts the core, releases input0 and verifies PAUSED/effective0/certain. If
uncertain, send no further traffic and report cleanup unverified. Keep the server
available briefly to show terminal status; process shutdown closes it. Do not
silently restart or reset an uncertain session.

## Operation and evidence

Before exposing a retained session, a bounded two-capture check verifies actual
metadata progression, native pixels and latency from the existing image. External
CLI checks must demonstrate unauthenticated rejection and authenticated PNG
hash/status freshness. Existing image identity is observed, not inferred from the
latest software source. No new gameplay, counter, physical monitor or long-run
milestone evidence is claimed.

A live viewer is an operational dependency. Preserve its worktree and private
runtime while running, or move it to a documented retained runtime before cleanup.
Do not delete or terminate it as ordinary merged-PR cleanup. The viewer is temporary and ends on its declared local shutdown. A manually
started user-owned tunnel is not changed or stopped by this worker.

The implementation caps concurrent HTTP handlers at8 with5-second socket timeouts,
keeps only32 recent capture records plus a total count, and never queues overlapping
UART captures. An image request carrying `v=<capture sequence>` returns409 if that
generation is no longer current; the page retries status instead of pairing a new
image with old metadata. Display capture age and capture-time RUNNING state; verified
terminal status reports PAUSED, while uncertain cleanup reports UNKNOWN.

Run a30-second capture proof first (`--seconds30`, whole supervisor60 seconds).
The initial operational viewing session uses3600 seconds, with30 seconds reserved
by the outer supervisor for setup/cleanup. This is a60-minute viewing lease, not a
new endurance milestone. Local `STOP` in the tagged live-viewer directory stops the
loop, releases the board and closes the server. Its private credential file and
tunnel binary remain outside committed source.


## Buffered buttons

The owner authorized local and authenticated phone requests through one queue.
Phone controls are eight tap buttons: Left, Right, Up, Down, A, B, Start and Select.
They have no automatic repeat or hold. The page reports accepted IDs or refusal.
The local CLI publishes only an active-high generated eight-button mask1..255 and
a duration1..1000milliseconds. It never accepts UART opcodes, memory writes, load,
reset, configuration or arbitrary file paths. No button request is generated
automatically. The bounded physical demonstration is Right1 for134milliseconds;
no Start, Select, reset or image load is used for that demonstration.

One shared producer lock reserves increasing integer sequence numbers and atomically
publishes complete requests in that order. At most16 pending requests are accepted;
submission fails when full or the runtime is stopped. The single UART worker claims
a frozen batch of up to16 currently published requests before each capture,
including the first. It executes that entire batch in FIFO order, then performs
SNAPSHOT and all READ_FRAME chunks. Arrivals during the batch or capture wait for
the next batch. Claimed requests are never replayed after a crash. Invalid records
are rejected without UART traffic. No unbounded drain can starve capture.

For one valid request the worker writes the mask, waits its bounded monotonic host
time (interruptible by local stop), then writes and verifies input0 before another
snapshot starts. The duration is approximate host time after the input acknowledgment,
not an exact emulated frame count. Scheduling and UART acknowledgment add latency;
a full16-entry local batch can extend refresh by about16 seconds. During input
processing, show PROCESSING INPUTS and the real age of the prior capture; it is
not a fresh capture. No key is intentionally held
through the roughly1.1second pixel readback. Normal failures and stop release input;
uncertain completion sends no further traffic and reports unverified release.

The queue is under the tagged private runtime. Stop and verify PAUSED/input0/certain
before changing the running worker's source; restart at a new tag after source review.
Preserve the user-owned tunnel across this transition.

Local submission example (no UART connection is opened by this command):

```powershell
python tools/fpga_viewer.py --tag <running-tag> --queue-mask 1 --press-ms 134
```

The CLI reports QUEUED plus its sequence, not executed success. The worker retains
`input-latest.json` with applied/cancelled/rejected status and verified release.
Each claimed file is removed after its outcome; a crash-left `.claimed` file is
never replayed. Capture/result metadata retains at most32 recent input receipts.

Admission is rechecked under the producer lock. Shutdown closes admission and
uses the same lock to record pending requests as CANCELLED without UART traffic.
A crashed producer lock fails closed with a manual-inspection error; it is never
automatically reclaimed. STOP-file waits are checked at most20ms apart, excluding
ongoing bounded UART commands.
