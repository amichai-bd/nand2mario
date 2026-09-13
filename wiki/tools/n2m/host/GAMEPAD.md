# On-screen Game Boy pad

Play the image already on the board from a local window, watching the board's
own VGA output. `python tools/fpga_viewer.py --gui` opens a desktop pad with a
D-pad and A, B, Select and Start; each control names the key that presses it.
The pad sends buttons and nothing else: it reads no frames, serves no HTTP and
never loads, resets or programs the board. The
[host contract](SPEC.md) owns UART, session and input semantics.

This is the third way to control the board, and the only one that shows the
controls. [`host keyboard`](SPEC.md#focused-keyboard) needs a Windows classic
console and shows nothing; the [live viewer](LIVE_VIEWER.md) shows pixels over a
tunnel but sends fixed taps. Use the pad when you are sitting at the board.

## Run it

Verify the [board setup](../../../src/board-bring-up.md), the selected healthy
UART endpoint, wiring and voltage first. The existing image must be valid, with
UART input authority and effective input 0. Keep device selectors and the build
identity in local variables, not in shared text.

```powershell
$PadPort = '<selected UART port>'
$PadBuild = '<reviewed 32-digit lowercase wire build ID>'
python tools/fpga_viewer.py --gui --expected-build-id $PadBuild --uart-port $PadPort
```

`--uart-vid`, `--uart-pid` and `--uart-identity` narrow the selection the same
way they do for every host command; exactly one healthy device must match.
Omitting `--tag` creates one unique tag and reports it. `--seconds` sets the
session lease, 900 seconds by default and at most 3600. Viewer-only options are
refused: the pad has no credentials, no HTTP port and no browser origin.

## Controls

| Control | Key | Mask bit |
| --- | --- | --- |
| Up, Down, Left, Right | Arrow keys | `BUTTON_UP`, `BUTTON_DOWN`, `BUTTON_LEFT`, `BUTTON_RIGHT` |
| A | `Z` | `BUTTON_A` |
| B | `X` | `BUTTON_B` |
| Select | Right Shift | `BUTTON_SELECT` |
| Start | Enter | `BUTTON_START` |

The mapping is `host keyboard`'s own table, imported rather than restated, so
the two commands cannot drift apart. Tk reports the same Windows virtual-key
codes it is keyed by; only the shift keys need a keysym, because both arrive as
`VK_SHIFT` and only the right one is Select.

A key down adds its button and a key up removes it. Chords and opposite
directions are preserved. Auto-repeat changes nothing, because a repeated down
leaves the union unchanged and writes nothing. Ctrl- or Alt-modified downs are
ignored; their releases still clear a held key. Escape or closing the window
exits.

Clicking a control presses it and releasing the mouse releases it, through the
same call a key uses, so a held click is a held key and the board cannot tell
them apart. A control lights up while it is held, whichever pressed it.

Each changed union is one ordinary `INPUT` write with its acknowledged dot
retained, exactly as `host keyboard` does. There are no fixed-duration taps and
no queue: hold means hold.

## Free-run only

The pad runs the core continuously and never pauses it. It resumes a paused
image once at startup, with neutral input, and leaves it running on exit.

The live viewer's stepped mode exists because a frame costs 5760 packed bytes
plus framing over a 115200 baud 8N1 link, about 11520 bytes per second, and a
measured viewer session captured about every 2.02 seconds. Nothing playable can
be seen through that, so stepped mode advances emulated time only when the
operator acts. The pad reads no frames, so that bound does not apply to it:
the player sees the board's VGA output at native rate and each press costs one
short `INPUT` exchange. Stepping here would only stop the picture, so the pad
offers no mode toggle. Use the [live viewer](LIVE_VIEWER.md) when you need
frames instead of a monitor.

## What the window reports

The window shows the held buttons by name, the current mask, how many writes
the session has sent and the dot the endpoint acknowledged for the last one.
Below that it polls the board itself, about every 400 ms, for the core state
(RUNNING or PAUSED) and the effective input. Those two lines are board answers,
not host guesses: when the effective input disagrees with the held union the
window says what the board reports. The remaining lease is shown while it runs.
A failed UART read or write stops the session, states the failure and closes
through the ordinary release path rather than playing on blind.

## Session, locks and exit

The pad reuses the session machinery the viewer owns: the canonical machine
lock, the durable per-device session and its sequence state, and the same
preconditions in the same order — expected build and ABI, valid image, UART
input authority, effective input 0, and a paused or running core. A failed
precondition sends no control traffic at all.

Only one trusted controller may hold the board. Starting the pad while the live
viewer, `host keyboard` or another pad is running fails before any input is sent
and names the actual cause, rather than a generic error: another trusted
controller holds the machine, or another session holds the device lock. An
uncertain durable session is refused the same way and must be recovered
explicitly.

On exit, whether by Escape, the window close, the lease expiring or Ctrl+C, the
pad writes `INPUT` 0 and reads the effective input back to verify 0 before
reporting release. If the Client is uncertain it sends nothing further and
reports that instead of claiming release. Unlike the viewer's STOP path it does
not `HALT` the core, because the player is watching the screen; like it, the
session ends certain, with a retained result and packet journal under the run's
build tag. Killing the process or unplugging the adapter cannot guarantee a
released mask.

## Verification

[`tools/n2m/tests/test_gui_pad.py`](../../../../tools/n2m/tests/test_gui_pad.py)
covers the mapping, the single write per changed union, repeats, chords, mouse
and keyboard equivalence, the request order through preflight and release, the
uncertain and failed-release paths, and the refusal message when the board is
already held. It runs against a fake endpoint with no board and no window. A
window cannot be asserted in CI; the layout, highlighting, mouse and key
handling and the exit path were exercised by hand against the real window with a
fake endpoint.
