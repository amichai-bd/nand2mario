# Live FPGA viewer

The viewer serves actual160x144 pixels of the software image already loaded on
the board. It never loads, resets or programs that image. A static image can be
fresh: capture and source-frame sequence, not visual change, establish freshness.
The [host command contract](SPEC.md) owns UART/session/snapshot semantics.

## Access

The local server binds only127.0.0.1. Its only routes are GET `/`, `/status.json`
and `/frame.png`, each requiring HTTP Basic authentication. It has no browser
control, UART write, configuration, upload or file routes. Responses disable
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
it with input0. It never supplies Start or gameplay input. Every capture is one
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
Do not delete or terminate it as ordinary merged-PR cleanup. The tunnel and viewer
are temporary and end together on the declared local shutdown.

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
