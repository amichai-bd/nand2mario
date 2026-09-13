# On-screen Game Boy pad

Play the image already on the board from a local window, watching the board's
own VGA output. `python tools/fpga_viewer.py --gui` opens a desktop pad with a
D-pad and A, B, Select and Start; each control names the key that presses it.
The pad sends buttons and nothing else: it reads no frames, serves no HTTP and
never loads, resets or programs the board. The
[host contract](SPEC.md) owns UART, session and input semantics.

The [launcher](LAUNCHER.md) is the way in for playing: it lists every loadable
game, loads the one you pick and hands over to this same pad inside one session.
Use the pad on its own when the image you want is already on the board.

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
Omitting `--tag` creates one unique tag; the startup line reports the tag, the
lease and the directory holding the run's `result.json` and packet journal.
`--seconds` sets the session lease, 900 seconds by default and at most 3600; the
window shows the remaining time and closes through the ordinary release path when
it expires. The pad enforces that lease itself rather than under the viewer's
process supervisor, because killing the process tree would bypass the release.

Viewer-only options are refused by name rather than ignored: `--credentials`,
`--init-credentials`, `--input-origin`, `--port`, `--interval`, `--step-frames`
and `--queue-mask` all belong to the frame viewer and have no meaning here.

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

Windows does not report that pair symmetrically: a right-Shift press arrives as
`Shift_R` and its release as `Shift_L`, on the same `VK_SHIFT` keycode. So **any
release on the shift keycode clears Select**, whichever keysym it carries, while
only `Shift_R` presses it. Left Shift therefore still never presses Select, and a
release with nothing held changes no union and writes nothing. Clearing a button
on an ambiguous release is safe; creating one is not.

A key down adds its button and a key up removes it. Chords and opposite
directions are preserved. Auto-repeat changes nothing, because a repeated down
leaves the union unchanged and writes nothing. Escape or closing the window
exits.

**Only Control and Alt suppress a press.** A key-down is ignored when the Tk
event state carries Control (`0x4`) or Alt (`0x20000`), matching `host keyboard`;
its release still clears a held key. No other state bit suppresses anything, and
in particular Shift, CapsLock, the extended-key flag and `Mod1` (`0x8`) do not.
`Mod1` matters: Windows latches **NumLock** into it, so while NumLock is on every
key event in the window carries `0x8`. Filtering it would drop every press and
pass every release, leaving the on-screen buttons working and the keyboard dead.

**Losing window focus releases every held button**, in one write, and the window
stays open and playable. Alt+Tab or a click on another window delivers the key-up
to that window instead, so without this the board would keep the button; the
player is watching the monitor, not the pad, and would see their character walk
on by itself with nothing on screen to explain it. `host keyboard` treats focus
loss as an exit condition because a console command has nowhere else to go; the
pad is the player's control surface, so it releases and waits rather than closing
mid-game. The window says so when it happens. A key-up that arrives later,
because focus returned before the key was let go, changes an already-empty union
and writes nothing.

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
(RUNNING or PAUSED) and the effective input. This poll is two word reads, and is
the only traffic the pad generates that `host keyboard` does not: it is what makes
the displayed state a board answer rather than a host assumption, and it stops at
the first failure. Those two lines are board answers,
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
covers the mapping, which state bits suppress a press and which must not, the
asymmetric right-Shift press and release pair, the single write per changed
union, repeats, chords, mouse and keyboard equivalence, focus-loss release and the stale key-up after it, the
lease, the board poll and its failure, the request order through preflight and
release, the uncertain and failed-release paths, and the refusal messages for a
held board and for viewer-only options. It runs against a fake endpoint with no board and no window. A
window cannot be asserted in CI; the layout, highlighting, mouse and key
handling and the exit path were exercised by hand against the real window with a
fake endpoint. Everything the window does other than drawing itself — input
edges, focus loss, the poll, the lease and the failure that ends a session —
lives in `Driver`, which is what those tests drive, and its widgets live in
`PadPanel`, so the [launcher](LAUNCHER.md) shows the same pad in its own window
without reimplementing any of it.
