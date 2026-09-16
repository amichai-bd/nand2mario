# DE10-Lite board bring-up

This records the proof that the connected DE10-Lite path is safe and
operational, using the existing `v05-board`
[target](../../src/fpga/de10_lite/targets.json) and UART host tooling. It
closes the UART-provable part of
[GAP-005](../preflight-gaps.md#gap-005-board-wiring-and-safe-bring-up):
documented wiring, signalling boundary, ground, pins and reset polarity, then
checked programming, heartbeat, frame content, ping, build ID and CRC
rejection. Nothing here is a meter or oscilloscope reading.

No agent has a monitor attached to this board, so every result in the run
record below is a UART-readable proxy or a static Quartus report. The board
owner separately connected a monitor and looked at the picture; that
observation and its limits are in [Display observation](#display-observation),
and it closes the display acceptance
[GAP-006](../preflight-gaps.md#gap-006-clock-reset-and-cdc-plan) held open.

## Wiring, voltage, ground, and reset polarity

The board is an Intel/Terasic DE10-Lite with a `10M50DAF484C7G` MAX 10 device,
driven over its onboard USB-Blaster for JTAG and an external 3.3 V UART
adapter wired to the Arduino header. All signals are single-ended 3.3 V LVTTL;
no level shifting is used or required.

| Function | Connector | FPGA pin | Direction |
|---|---|---|---|
| UART receive (adapter TX to FPGA RX) | Arduino D0 | `PIN_AB5` | input |
| UART transmit (FPGA TX to adapter RX) | Arduino D1 | `PIN_AB6` | output |
| Board reset, active low | KEY0 | `PIN_B8`, 3.3 V Schmitt trigger | input |
| VGA red[3:0] | VGA connector | `PIN_AA1`, `PIN_V1`, `PIN_Y2`, `PIN_Y1` | output |
| VGA green[3:0] | VGA connector | `PIN_W1`, `PIN_T2`, `PIN_R2`, `PIN_R1` | output |
| VGA blue[3:0] | VGA connector | `PIN_P1`, `PIN_T1`, `PIN_P4`, `PIN_N2` | output |
| VGA hsync, active low | VGA connector | `PIN_N3` | output |
| VGA vsync, active low | VGA connector | `PIN_N1` | output |
| Reference clock | onboard 50 MHz oscillator | `PIN_P11` | input |

These pins come from the committed `v05-board` [target definition](../../src/fpga/de10_lite/targets.json)
and match the [DE10-Lite user manual](https://www.terasic.com.tw/cgi-bin/page/archive.pl?Language=English&CategoryNo=205&No=1021)
pinout for KEY0, the VGA connector, and the Arduino header. The UART adapter's
ground is tied to the DE10-Lite ground pin on the Arduino header; both boards
share a common ground through that connection and through USB to the same
host. `board_reset_n` uses the DE10-Lite's onboard Schmitt-trigger KEY0 input,
so no external reset wiring is used and no reset polarity inversion exists
outside the FPGA fabric. The design released from reset and answered over UART,
which shows the released level is not inverted; nobody pressed KEY0, so its
asserted direction is unverified and needs physical presence.
UART RX/TX direction was confirmed by the adapter's
own TX/RX labeling and by a successful `PING` round trip (below); a swapped
pair produces silence, not a false pass, because `PING` requires a matching
response sequence and CRC.

Record measured supply, ground continuity, and connector identity in each
physical run's evidence, per the [electrical boundary](fpga-controls.md#electrical-boundary)
precedent for the separate ADC/button header. No unidentified module, 5 V
digital output, or unknown terminal order is connected to this board.

## Programming

Programming always checks the attached JTAG identity before writing a
bitstream. `n2m fpga program` requires `jtagconfig` to report exactly one
selected USB-Blaster chain whose device name matches `10M50DA`, the same check
`doctor.py` already performs read-only in its `environment` profile.
Programming refuses to run if zero or more than one matching chain is present,
and refuses a `.sof` path that is missing, a symlink, or outside the
repository. It does not inspect the bitstream's own target device: a `.sof`
built for a different device is refused by `quartus_pgm` itself, which checks
the file against the device it finds on the chain. `quartus_pgm` is invoked in
JTAG mode with `-o "p;<sof>"`; a nonzero exit, or output without its explicit
success line, fails the run before any host traffic is attempted. The command
is normally run from Windows PowerShell inside the WSL checkout over its
`\\wsl.localhost\<distro>\...` UNC path with the `.sof` given as the
repository-relative path `fpga build` printed; the
[record](../tools/n2m/SPEC.md#program-records) stays repository-relative and
portable, and a failed record names its `device_state` (`unchanged`,
`changed` or `unconfirmed`) so the operator, not the tool, decides on a
second programming pass.

### Flash programming procedure

The [flash library](rtl/storage/MAS_flash_library.md#programming-the-flash)
is written into the MAX 10 internal flash with `fpga program --pof`, under the
same identity check and the [flash record rules](../tools/n2m/SPEC.md#flash-programming).
The procedure for a board session, which needs its own authorization and the
exclusive board lock:

1. Build the flash image on Windows:
   `python tools/build.py fpga build flash-proof --quartus-bin <Quartus-bin> --tag <tag>`.
   The result names `output/design.pof`; the record shows `configuration_mode`
   `Single Comp Image` and a passing `.pof` check.
2. Prove the record and the command without touching the board:
   `python tools/build.py fpga program --pof <pof> --dry-run --quartus-bin <Quartus-bin> --tag <tag>`.
   The line written to `dry-run.log` is
   `quartus_pgm -c <cable> -m jtag -o pvb;<pof>` (the argument list without
   shell quoting).
3. With the UART adapter disconnected and only the USB-Blaster attached, run
   the same command without `--dry-run`. `jtagconfig` must report one
   USB-Blaster chain with a `10M50DA`; `quartus_pgm` programs, verifies and
   blank-checks CFM0 and the user range. The result records `isp_seconds`,
   `pof_sha256`, the chain and `program.log` under `fpga-program/<id>/`.
4. Power-cycle the board with no host attached and observe the monitor. A
   bitstream that carries the [boot copier](rtl/storage/MAS_flash_library.md#boot-copier)
   (`v05-board`) shows the menu from flash; the `flash-proof` image itself holds the library and the
   reader only. The session's UART input is
   [`host library load`](../tools/n2m/host/SPEC.md#commands) of every image
   the [registry](../tools/n2m/SPEC.md#flash-library-image) builds, the
   `sw library` attempt's package results with the menu as `--menu`, so the
   loaded library and the flash-resident one carry the same catalogue.
5. Record the session under [Run record](#run-record): the attempt commit,
   the `.pof` hash, `isp_seconds`, the observed picture and whether the
   flash content changed. No session has run yet
   ([#694](https://github.com/amichai-bd/nand2mario/issues/694)).

Programming the flash changes the board's power-up configuration: the next
`fpga program --sof` still configures the device volatile for that power
cycle, and the flash image returns at the next power-up.

## Heartbeat and VGA test-card proxies

[`board_bringup.py`](../../src/dv/springtrail/board_bringup.py) proves both.
Neither result is verified by eye; both come from the already-loaded
`v05-board` system over UART, under the exclusive
[machine lock](../../tools/ci/storage.py) and durable session
[`endurance.py`](../../src/dv/springtrail/endurance.py) already uses for the
continuous milestone:

- **Heartbeat.** After a fresh `LOAD`, the endpoint sits at dot 0. `RUN_DOTS`
  is issued for bounded, exact counts until the target dot is reached; the
  returned dot count must be greater than zero. This proves the reference
  clock, PLLs, reset release, and CPU/timebase datapath are alive end to end,
  read back over the same UART path used for every other check.
- **VGA test card.** The current build's original springtrail ROM (built
  fresh from source by `build_rom`, not a frozen historical fixture) is
  loaded and run to its title frame. The frame is read back with
  `SNAPSHOT`/`READ_FRAME` and compared, pixel for pixel, against
  `endurance.expected('title')` — the same independent reference the
  continuous milestone (#264) already checks. This is the same deterministic
  image the frame bridge scans out to the physical VGA pins; its CRC and full
  pixel match are the test-card proxy in place of an observed picture. The
  precise per-scanline freshness window `endurance.py` also checks depends on
  a hand-maintained LCD-commit constant this run does not attempt to
  recalibrate; the full pixel match is the actual proof here, and a stale
  constant or wrong captured frame fails it rather than passing silently.
- **Pin-level timing.** The `v05-board` Quartus build already produces
  `design.sta.summary`/`design.sta.rpt` timing closure for the VGA, UART, and
  clock pins listed above, with `output_delay` constraints recorded in
  `targets.json`. That closed-timing report is the pin-level timing evidence;
  it is a static analysis result, not an oscilloscope measurement.

## UART ping, build ID, and CRC rejection

Register `BUILD_ID_0` holds `BUILD_ID[31:0]`, the *least*-significant word of
the 128-bit `N2M_V05_BUILD_ID` Verilog literal
([`n2m_uart_host_registers.sv`](../../src/rtl/uart/n2m_uart_host_registers.sv)).
`identify()` concatenates `BUILD_ID_0..3` little-endian in register order, so
the wire hex string is the full byte-reversal of the `fpga build` record's
`build_id` field (itself the literal's leading 32 hex characters). Compare
against a value obtained from `identify()` — this run's or a previously
recorded one — not against the build record's `build_id` string directly.

`Client.identify()` sends `PING`, reads the ABI register, and reads the four
`BUILD_ID` words, failing if any check disagrees or the identity is all zero.
[`crc_proof.py`](../../tools/n2m/host/crc_proof.py) sends one `PING` with a
flipped CRC byte and requires silence (no response), then proves a following
well-formed `PING` still succeeds and that all public state and counters are
unchanged. Both run under the same session and exclusive lock as the heartbeat
and test-card checks.

## Live DMG I/O register session

`host io --samples 600` on the programmed `v05-board` build read the exposed
[DMG I/O view](../tools/n2m/host/SPEC.md#dmg-io-register-view) while the v0.5
program ran, with no pause and no step. The endpoint stayed in RUNNING and the
dot counter increased strictly across all 600 samples, spanning 82,030,780
dots, about 1,168 frames.

The capture covered 150 of the 154 scanlines, including VBlank. Every sample
with LY 144 or above reported STAT mode 1 and no sample on lines 1 to 143 did,
so the mode progression across a frame matches expectation. STAT bit 7 never
read back set across all 600 samples, confirming the committed-storage rule the
table states, and LCDC read `0x91` in every one of them. BGP `0xE4` and IE
`0x01` come from the single closing pass over the whole register set, not from
every sample. All three are the exact values the program writes to FF40, FF47
and FFFF.

Four samples reported LY 0 with mode 1. That is the documented LY153 early wrap
described in [MAS_ppu](rtl/ppu/MAS_ppu.md): readable LY returns to 0 early on
line 153 while the PPU is still in VBlank, and a CPU read sees the same value.
Simulation does not reach VBlank inside its wall budget, so this window is
observed here and not there.

The session left the board PAUSED with input 0 and a valid image.

## Run record

Each physical run's evidence records the exact bitstream commit and whether
board state changed:

- The commit is the `commit` field of the `fpga build` record that produced the
  programmed `.sof`, alongside that record's `fingerprint`/`build_id`.
- Board state changed exactly when `n2m fpga program` ran. Programming
  reconfigures the device unconditionally — nothing reads the board's current
  identity first, because `program()` never opens the UART — so a run that
  programs has changed board state, and a run that reuses an already-configured
  board has not. The programmer's retained `program.log` is the record of which
  happened.
- After programming, `board_bringup.py` calls `identify()` and fails unless the
  running wire `build_id` equals the expected one. That is a post-programming
  confirmation that the intended build is live, not a decision about whether to
  program.

The evidence closing this gap: `jtagconfig` reported exactly one USB-Blaster
chain with device `10M50DA(.|ES)/10M50DC` before programming;
`n2m fpga build v05-board` built commit `7338daed81370ce7794eae4eae8c292c23ca5610`
(wire build ID `ba1d1956ca07a2c38aae5c801e217f98`, the byte-reversal of the
build record's `987f211e805cae8ac3a207ca56191dba`); `quartus_pgm` reported
"Quartus Prime Programmer was successful. 0 errors, 0 warnings", changing the
board's prior configuration; the board was then programmed fresh a second time
so the physical run's epoch started clean. `board_bringup.py` then passed in
full over COM3: heartbeat dot 283932, test-card pixel match on all 23040
pixels (CRC32 `9b162de2`), UART ping/ABI/build-ID identity confirmed, and CRC
rejection silent then recovered with unchanged public state and counters. Total
wall time was 15.3 s, inside the 120 s budget. See the PR for the retained
run evidence.

## Game library sessions

Three owner-authorized sessions proved the merged game-library slices on the
board: the host loads the library into SDRAM, the loader profile swaps images
and resets the core, the menu runs from the fitted volatile bitstream, and every
frame named below was read back with `SNAPSHOT`/`READ_FRAME` and compared pixel
for pixel against an independent reference. As everywhere on this page, the
pixel-exact UART readback is the display proxy; no monitor was attached. The
[acceptance table](#game-library-acceptance) maps each criterion to its record.

Authorization. On 2026-09-16 the owner pre-authorized the sessions with the
same scope: the COM7 UART adapter and the onboard USB-Blaster, a volatile
`.sof` only, no flash programming, readback through `SNAPSHOT`/`READ_FRAME`,
and pixel comparison against the independent references. On the same day the
owner accepted Springtrail as the independent reference game for the started
title frame: the other loaded games start and their frames are retained, but
no independent title reference exists for them yet. The physical KEY1 press
was performed by the owner at the board (session 3).

References. Menu frames are compared with
[`reference.py`](../../src/dv/menu/reference.py), composed from the
[menu layout rules](sw/menu/SPEC.md#frame-layout) and the catalogue bytes
that `host library status` retains, never from the ROM or the board. The game
title is compared with `endurance.expected('title')` from
[`endurance.py`](../../src/dv/springtrail/endurance.py), the reference the
[test-card proxy](#heartbeat-and-vga-test-card-proxies) already uses. Each
comparison was recomputed a second time on a different machine from the copied
`frame.2bpp` with the same result. Record identifiers below are the host tool's
record ids under the session build tags; the retained set, its provenance and
the rendered frames are linked from the closing PR.

### Session 1: direct-profile swaps

The commit had no loader-profile menu image yet, so Springtrail was loaded as
the index-16 image with the direct profile and the host return
(`WRITE_HOST(LIBRARY_CONTROL)`, defined by the
[loader contract](rtl/cartridge/MAS_loader_profile.md#host-interaction) as the
same swap `key1_return` performs) exercised the SDRAM-to-ROM swap path.

- Git commit: `main` `f84fd1563d3461e63a2972c04784da7dede21465`; the three game
  packages were built at the same commit (tag `681-sw`).
- Fit: `v05-board` attempt `cc1736dd1eee` (tag `681-fit`), status `PASS`,
  build id `772057b833b602fe73cf3ecb9b8892f5`, wire build id
  `f592889bcb3ecf73fe02b633b8572077` reported by every host record;
  `design.sof` SHA-256 `786d068e716c24151a008cbd4344b1d84612278c86ec4ef44938fc14304c1a95`;
  unconstrained paths none, ignored constraints none, worst slack 0.118 ns
  (fast-corner hold on the system PLL clock).
- Quartus version: Prime 25.1std.0 Build 1129 SC Lite Edition, for fit and
  programmer.
- Programming: `fpga-program/24b1709d76e2`, `quartus_pgm -c 1 -m jtag -o p;<sof>`
  against `10M50DAF484@1`, "Quartus Prime Programmer was successful. 0 errors,
  0 warnings", 3 s. An earlier attempt `70d1f09ec525` had programmed the same
  bitstream successfully, but its record step rejected a relative `.sof` path,
  so programming was repeated with an absolute path. Board state changed twice.
- Wiring: the documented UART and JTAG connections above; nothing was rewired.

| Step | Record (tag `681-board`) | Result |
|---|---|---|
| `host library load` stackdrop, v05, springtrail, `--menu` springtrail | `library-load/b6823421513b488ea8478ef5093e7713` | 4 images, catalogue `PASS`, `mismatch_count` 0; CRC32 `619fa99f`, `718b0dcb`, `8b564649`, `8b564649` equal the readback |
| `host library status` | `library-status/a813b74161c242ffb49605ba0b1166d1` | catalogue identical; `LIBRARY_STATUS` `$A000` 0x20 (`sdram_ready`), result `NONE` |
| Host return from a host-paused console | `write/1c691f97b1064c4d813ecd4db7f3d824` | swap completed: `IMAGE_VALID` 1, `PROFILE` 1, result `OK`; the console stayed `PAUSED` and `host snapshot` reported `NO_FRAME` |
| `host run`, `host snapshot` | `snapshot/0ee64e6bbc224b8f95246ee565b6b211` | epoch 1; 23040 pixels, 0 mismatches against `expected('title')`, CRC32 `4a3bad02`; frame SHA-256 `2fceba2fa96842903b90bd2bf906235549bf25a556cc3765110b2243a651d605` |
| Host return while `RUNNING` | `write/6a4cbfff9a01442ba27baf02eb42cb14` | swap completed, result `OK`; the console resumed `RUNNING` without a host `RUN` |
| `host snapshot` | `snapshot/531ea02744564c7b8fd98bf1a1b3c555` | epoch 2; pixel-exact title frame again, same CRC32 and SHA-256 |

Board state after the session: programmed with the session bitstream, console
running Springtrail.

### Session 2: menu, host-injected joypad selection and return

- Git commit: `main` `5a79bd91fb80f151583487c79391a3ac7a2c9de0`; packages
  `menu` (`dmg-loader-v1`, profile id 2, ROM SHA-256
  `88a2206f209c3e4955098fc0654646270a1c6d12a23f66af339345cb78a33ed2`),
  `stackdrop`, `springtrail` and `v05` built at the same commit (tag `681b-sw`).
- Fit: `v05-board` attempt `e315fd07a215` (tag `681b-fit`), status `PASS`,
  build id `90f7b82be13496042dfabf43106558ee`, wire build id
  `ee58651043bffa2d049634e12bb8f790` reported by every host record;
  `design.sof` SHA-256 `957c37062a21cf9c570dbdda86a1c0e369cf9f89943fea09169035e1783aadd6`;
  unconstrained paths none, ignored constraints none, worst slack 0.152 ns
  (fast-corner hold on `clk_reference`).
- Quartus version: Prime 25.1std.0 Build 1129 SC Lite Edition.
- Programming: `fpga-program/6838f769940a`, the same command against
  `10M50DAF484@1`, "Quartus Prime Programmer was successful. 0 errors,
  0 warnings", 4 s. Board state changed once.
- Wiring: unchanged.

The host records under tag `681b-board` are timestamped 2026-09-15 23:47 to
23:54 UTC. `host status` right after programming read `IMAGE_VALID` 0,
`PROFILE` 0 (`status/1f7978ad…`).

| Step | Record (tag `681b-board`) | Result |
|---|---|---|
| `host library load` stackdrop, springtrail, v05, `--menu` menu | `library-load/53678d3c561c4d50a7243e870ce3c913` | 4 images, catalogue (1024 bytes at 557056) `PASS`, `mismatch_count` 0; slots 0 `STACKDROP` `619fa99f`, 1 `SPRINGTRAIL` `8b564649`, 2 `V05 BUTTONS` `718b0dcb`, 16 `GAME MENU` profile 2 `ec9c63fe`, each equal to its readback CRC32 |
| Host return (`WRITE_HOST(LIBRARY_CONTROL)` 1) from the paused console | `write/aaf2124c…`, `status/1b2ac5d1…` | menu swapped in: `IMAGE_VALID` 1, `PROFILE` 2, `STATE` paused |
| `host run`, `host status`, `host library status` | `run/15846d6f…`, `status/39350634…`, `library-status/db747176d248471494b68699369fbe78` | `STATE` running; `$A000` 0x60 (`window_ready`, `sdram_ready`), result `OK`; catalogue SHA-256 `15fe956cb3b7fa66be36f766873de6f620ceb4c3c42341fcc6f1a4e8887649a3` |
| Menu frame | `snapshot/ba40d05617a44d5bb05ecff7b94678bc` | epoch 1; pixel-exact `expected('menu')`: 23040 pixels, 0 mismatches, CRC32 `c3753fdc`, frame SHA-256 `373f18d5d978be4762330a11a5f02d36f12ee06f23045dfc0e1fe7b3959b022d`; header, slots 00-15 with the three titles, cursor on 00 |
| Host-injected joypad Down (`host input --mask 8`, then release) | `input/7b01ef7d…`, `input/d64d6fa2…`, `snapshot/55c55e6b2cd14c7fa1af6b389a3920eb` | pixel-exact `expected('cursor-1')`, CRC32 `b56eb400` |
| Host-injected joypad A on slot 1 | `input/df5e447e…`, `input/7c8e9359…`, `status/6f375a01…`, `library-status/c05069ef…` | the menu wrote the select register; the loader swapped slot 1: `PROFILE` 1, running, result `OK` index 1 |
| Started game frame | `snapshot/721995456db14e32a32c57514aa409eb` | epoch 2; pixel-exact Springtrail title, CRC32 `4a3bad02`, frame SHA-256 `2fceba2f…` (the session 1 frame) |
| Host return | `write/9ab81d26…`, `status/f5cfc9cd…`, `library-status/fd1d2c71bce346e89f867ea0fc4b32dd`, `snapshot/58a8f84a682e4ac29aee4fdd4d90af6b` | menu back: `PROFILE` 2, running without a host `RUN`, epoch 3; pixel-exact menu frame, CRC32 `c3753fdc` |
| A on slot 0 (stackdrop) | `input/6efdeea9…`, `input/09f60588…`, `status/a5407164…`, `library-status/11477654…`, `snapshot/039c49df10794a58a880cb17ed06cca1` | swap `OK` index 0, epoch 4, running; frame retained (SHA-256 `29fba9b0e546dd5cc1112a8c880a496f94c77bd789b4582b3ec4a0cd077a54ae`), no independent reference |
| Return, Down, Down | `write/9eeeb1a4…`, four `input/…`, `snapshot/192bfb6a455a4e22bdbfb64404a8b523` | epoch 5; pixel-exact `expected('cursor-2')`, CRC32 `5cdbf106` |
| A on slot 2 (v05) | `input/70ab916f…`, `input/cefca414…`, `status/455e2da4…`, `library-status/6e21cf8e…`, `snapshot/4f2179d926594923ae19daef8bee40bf` | swap `OK` index 2, epoch 6, running; frame retained (SHA-256 `bc51aaa8ca4c10ff75b9845766eb05094866a150a9707fc0aaf3ae966d041d3f`), no independent reference |
| Final host return | `write/233e81cb…`, `status/4b90436c…`, `snapshot/6770ea0663564f589be22674ed13a4da` | `PROFILE` 2, epoch 7; pixel-exact menu frame, cursor 0, CRC32 `c3753fdc` |

Board state after the session: programmed with the session bitstream, menu
running from SDRAM.

Rendered frames, native 160x144 PNGs encoded from the retained `frame.2bpp`
bytes and published as durable PR attachments (PNG SHA-256 in parentheses):
[menu after load](https://github.com/user-attachments/assets/97251a2c-9b0c-477e-878a-0cdaa8886399)
(`2dee0801…`),
[cursor 1](https://github.com/user-attachments/assets/d1c56c91-5c5f-4b9a-94d3-7256f1e03bd6)
(`def28b6c…`),
[Springtrail title](https://github.com/user-attachments/assets/0e462b04-19ad-4d59-8a2b-02289cce1129)
(`505b95f0…`),
[menu after return](https://github.com/user-attachments/assets/293026f8-7f83-4e59-a858-4c8f69da60a1)
(`2dee0801…`, the same bytes as the menu after load),
[cursor 2](https://github.com/user-attachments/assets/42fb889a-c336-408a-b2c7-75301b4d0a4c)
(`d3673cd1…`) and
[final menu](https://github.com/user-attachments/assets/e8f8daaa-90a0-41ca-80f2-a39d7f2b8a82)
(`2dee0801…`). The diff renders are byte-identical to their frames because no
pixel differs.

Observation from both sessions: a swap requested while the console is
host-paused completes (`IMAGE_VALID`, `PROFILE`, epoch and `LIBRARY_STATUS`
update) but leaves the console paused until the host sends `RUN`; a swap
requested while running resumes on its own. Both match the
[core reset sequencing](rtl/cartridge/MAS_loader_profile.md#core-reset-sequencing-and-image-validity)
of the contract.

### Session 3: physical KEY1 return with the owner at the board

Same bitstream and board state as session 2: `v05-board` from `main`
`5a79bd91fb80f151583487c79391a3ac7a2c9de0`, build id
`90f7b82be13496042dfabf43106558ee`, wire build id
`ee58651043bffa2d049634e12bb8f790` reported by every record; no reprogramming,
so board state did not change. The owner was present and pressed KEY1
(`PIN_A7`) by hand; records under tag `681c-key1`, timestamped 2026-09-16
05:07 to 05:25 UTC. Menu frames are compared as in session 2, with the
catalogue bytes from the `host library status` record taken beside each
snapshot; the same catalogue SHA-256 `15fe956c…` as session 2.

| Step | Record (tag `681c-key1`) | Result |
|---|---|---|
| Earlier KEY1 presses from the menu | `status/8658981a…`, `library-status/7564086d…`, `snapshot/15d571db01b54b99abc376de4ed3802c` | `PROFILE` 2, running, result `OK`; epoch 12 where session 2 ended at 7, so each press restarted the menu through the return path; pixel-exact menu frame, CRC32 `c3753fdc`, frame SHA-256 `373f18d5…` |
| Stackdrop running at 05:21 UTC, started from the menu by the owner through the display viewer's own UART session | `status/13de9b2e…`, `library-status/47048d1e…`, `snapshot/357c2afe30b04a06888671796bcfa12e` | `PROFILE` 1, running, result `OK` index 0, `$A000` 0x20; epoch 21 (12 after the earlier presses); no host record of the selection exists under this tag; game frame retained (SHA-256 `c54654fbfe502e02a37434f475b96d9b372847e024bb30d0270dc617fffe3da9`) |
| Owner held KEY1 about 0.5 s | `status/50713275…`, `library-status/a4b92a33…`, `snapshot/b37001933af141a6abb3c8e68c125b0d` | back in the menu: `PROFILE` 2, `IMAGE_VALID` 1, running, epoch 22, result `OK`, `$A000` 0x60 (`window_ready`, `sdram_ready`); pixel-exact menu frame, 23040 pixels, 0 mismatches, CRC32 `c3753fdc`, frame SHA-256 `373f18d5…`, byte-identical to the session 2 menu frame and its published render |

Between the first two rows the owner's display viewer held the UART port
(05:09 to 05:21 UTC) and issued the selection that started Stackdrop; it keeps
no host record under this tag. The four `host input` attempts made in that
window failed to open the port, changed nothing on the board and are retained
as failures. The owner also watched the game start and the long press return
to the menu on the viewer; that observation carries the same limits as the
[display observation](#display-observation) below.

### Game library acceptance

| Criterion | Evidence | State |
|---|---|---|
| Library load with zero mismatches for every slot and the catalogue; `host library status` matches | session 2 `library-load/53678d3c…`, `library-status/db747176…` (and session 1 `library-load/b6823421…`) | proven |
| Menu frame pixel-exact after a host library load | `snapshot/ba40d056…`, CRC32 `c3753fdc` | proven |
| Selection of a loaded slot through the host-injected joypad path (`host input`) starts that game | `snapshot/55c55e6b…` (cursor), `library-status/c05069ef…` (swap `OK` index 1), and the slot 0 and slot 2 swaps | proven |
| Started game title frame pixel-exact | `snapshot/72199545…`, CRC32 `4a3bad02` (Springtrail, the accepted reference game; stackdrop and v05 frames retained without a reference) | proven |
| Return to the menu with a pixel-exact menu frame | host return `write/9ab81d26…` then `snapshot/58a8f84a…`, and the final return `snapshot/6770ea06…` | proven through the host return |
| Physical KEY1 hold returns to the menu with a pixel-exact menu frame | session 3 `snapshot/357c2afe…` (Stackdrop running, epoch 21) then the owner's 0.5 s hold and `snapshot/b3700193…` (menu, epoch 22, result `OK`, CRC32 `c3753fdc`); earlier presses `snapshot/15d571db…` | proven, owner present |

## Display observation

On 2026-09-13 the board owner connected a monitor to the DE10-Lite VGA output,
looked at it, and reported the picture as correct: "I see the Stackdrop
picture! score state etc.. all looks good."

Conditions at the time of the observation:

- Wire build `87d5f0280a2afad8be6b85dc601141cc`, ABI 1: the already-programmed
  build reused for that session, not the build in the run record above.
- Loaded image: restyled Stackdrop, SHA-256
  `f2a9b159743a202541dd17dedaa99ffcc7ebf6d9d7012b28f4701a0ac9aed927`, 32768
  bytes, profile `dmg-direct-v1`, built from `main` at `1b18cfc2`. Loaded with
  `host load --package`, all 32768 bytes verified on readback, then
  `host reset`.
- The score and STATE readouts were legible, and the picture matched what the
  same image renders in the independently generated previews.

This is one direct visual observation by the owner at the board, not an
instrumented measurement: the monitor model, cable and reported mode were not
recorded, and no timing or signal quality was measured. It answers the question
the gap register held open, and nothing wider — a monitor locks to this signal
and shows the correct image for this bitstream and this loaded image. It makes
no claim about other monitors, cables, modes or scaled operation, and does not
replace the pixel-exact UART readback above. The image on screen was the loaded
Stackdrop frame; the VGA test card was not displayed. Tolerance across displays
stays with [GAP-012](../preflight-gaps.md#gap-012-vga-frame-crossing).

## Open items

Pressing KEY0 and recording the board reset still needs hands at the board,
tracked by [#512](https://github.com/amichai-bd/nand2mario/issues/512).
