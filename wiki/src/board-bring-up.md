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
which shows the released level is not inverted. The asserted direction was
observed on 2026-09-16 with the owner at the board: pressing KEY0 reset the
whole design and releasing it brought the design back, answering over UART
with the same build identity, twice
([KEY0 board reset](#key0-board-reset)).
UART RX/TX direction was confirmed by the adapter's
own TX/RX labeling and by a successful `PING` round trip (below); a swapped
pair produces silence, not a false pass, because `PING` requires a matching
response sequence and CRC.

The 3.3 V above is a per-pin record, not an assumption. The
[DE10-Lite registry](../../src/fpga/de10_lite/targets.json) records
`3.3-V LVTTL` against every package pin this repository places on this board, and
[`fpga.py`](../../tools/n2m/fpga.py) takes each assignment from there; a pin the
registry does not record refuses the build instead of defaulting to a voltage.
`board_reset_n` and `key1_n` restate that same recorded voltage as its
Schmitt-trigger input, which is the board's onboard KEY buffer. This is the one
board where the declared standard has been exercised physically: every image in
the [run record](#run-record) below was programmed with it and answered.

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
   flash content changed. The
   [flash-resident boot sessions](#flash-resident-boot-and-sdram-sweep-sessions)
   below are the sessions run so far.

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

Four owner-authorized sessions proved the merged game-library slices on the
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

### Session 7: game exit register from a host-loaded image

The [game exit register](rtl/cartridge/MAS_loader_profile.md#game-exit-register)
on the board: the built [`exit-demo`](../../src/sw/exit-demo/main.asm) image
(title `EXIT DEMO`, `dmg-direct-v1`; a solid bar on map row 8, and while
Start is held one write of `$10` to `$6000` per frame) was host-loaded into
library slot 3 beside our three games, started from the menu through the
host-injected joypad, and returned to the menu by its own write. The game
frame is compared byte for byte with the fixture's independent reference
(`fixture.exit_frame()` in [`fixture.py`](../../src/dv/menu/fixture.py):
pixel rows 64..71 shade 3, the rest shade 0), the menu frames with
[`reference.py`](../../src/dv/menu/reference.py) against the catalogue bytes
of the `host library status` record, as in session 2. The flash-resident
session 6 bitstream stayed programmed; no flash or Quartus action was needed
because the image is loaded over UART, and this change touched no RTL. No monitor
observation was recorded; nobody was at the board.

- Git commit: branch `739-exit-register-board` at
  `76aecd23bbbf10ad53df0c2453ee700730008280` (software, fixtures and
  documentation on `main` `31ba64e`); packages `springtrail`
  (`d8518b8d`), `stackdrop` (`818978e1`), `v05` (`718b0dcb`), `exit-demo`
  (ROM SHA-256
  `06ed18c4e4ab8330c529ec26d7d79ddba57e4e351c43a401b10fb74ad1d89667`, CRC32
  `1161403e`) and `menu` (`a5d8a00f`) built at the same commit (tag
  `739-sw`).
- Fit: unchanged, `v05-board` attempt `d3352b4ff0fb` (tag `738-fit`), build
  id `2f671a6f2216860496e024e2954b712b`, wire build id
  `2b714b95e224e096048616226f1a672f` reported by every host record.
- Programming: none; the flash content and the board state did not change.
- Wiring: unchanged; the owner's display viewer released COM7 before the
  session and the host records were taken with no hands at the board.

Records under tags `739-board-*`, transaction stamps 2026-09-16 20:45:04 to
20:54:16 UTC (23:45 to 23:54 board clock, UTC+3). The owner's viewer had left the endpoint `PAUSED`, so the first
scripted attempt stopped at its menu snapshot (`739-board-menu0`, `SNAPSHOT`
rejected with status 7: no frame while paused) with no board state changed,
and the baseline `host status`/`host library status` attempts
(`739-board-status0`, `-libstatus0`, `-libstatus0b`) failed to open the
session while the viewer's lock still existed; they are retained as failures.
The library return record carries the baseline instead.

| Step | Record (tag `739-board-<step>`) | Result |
|---|---|---|
| `host library load` springtrail, stackdrop, v05, exit-demo, `--menu` menu (`libload`) | `library-load/2dab13a5…` | 5 images, catalogue `PASS`, `mismatch_count` 0; slots 0 `SPRINGTRAIL` `d8518b8d`, 1 `STACKDROP` `818978e1`, 2 `V05 BUTTONS` `718b0dcb`, 3 `EXIT DEMO` `1161403e`, 16 `GAME MENU` profile 2 `a5d8a00f`, each equal to its readback CRC32 |
| `host library return --wait` (`return0`) | `library-return/608d9133…` | baseline and return: `PROFILE` 2, `IMAGE_VALID` 1, `STATE` `PAUSED` (the viewer's state), result `OK`, `$A003` 7 from the viewer's earlier selection, `$A000` 0x28 (`sdram_ready`, `flash_boot`); settled |
| `host run` (`run0`), `host status` (`status1`), `host library status` (`libstatus1b`) | `run/a53636a5…`, `status/61040e04…`, `library-status/7d3d7b6b…` | the `RUN` was needed only because the endpoint was host-paused; `STATE` running, `PROFILE` 2; `$A000` 0x68 (`window_ready`, `sdram_ready`, `flash_boot`), result `OK`, `$A003` 7; catalogue SHA-256 `1b3bf46e…`, the four titles above and the menu |
| Menu frame (`menu0b`) | `snapshot/24a39197…` | epoch 29, seq 601; pixel-exact `expected('menu')` for that catalogue: 23040 pixels, 0 mismatches, CRC32 `bee303ec`, frame SHA-256 `d9b6cc8e…`; cursor 0 |
| Down, Down, Down (`down1b`..`down3b`, each `host input --mask 8` then `--mask 0`), menu frame (`menu3b`) | `input/1a230ee6…`, `input/a255d871…`, `input/b48a4196…`, `input/3a03b9f3…`, `input/e2e93c42…`, `input/dcc9589a…`, `snapshot/8c965c6e…` | epoch 29; pixel-exact `expected('cursor-3')`, 0 mismatches, CRC32 `8a530790`, frame SHA-256 `bc60fc9c…` |
| A on slot 3 (`select-a`: `--mask 16`, `--mask 0`), `host status` (`status-game`), `host library status` (`libstatus-game`) | `input/dda68ec0…`, `input/b0747103…`, `status/2393e022…`, `library-status/eadb2502…` | the menu wrote the select register and the loader swapped slot 3: `PROFILE` 1, `IMAGE_VALID` 1, running, result `OK` index 3, `$A000` 0x28 (`window_ready` cleared by the swap) |
| Game frame (`game`) | `snapshot/d2747973…` | epoch 30, seq 916; 5760 packed bytes, SHA-256 `8460305748df8e55afe9f5f47c1389a033c0c161f3f6f3c321935ce17ba2978c`, byte-identical to the independent `exit_frame()` reference (`exit-frame.2bpp`): the bar on pixel rows 64..71 |
| Start (`start`: `--mask 128`, then `--mask 0`), `host status` (`status-exit`), `host library status` (`libstatus-exit`) | `input/bdb5446b…`, `input/5e6e61c2…`, `status/daec2992…`, `library-status/011d3a65…` | the game wrote `$10` to `$6000`; the menu is back with no host `RUN`: `PROFILE` 2, `IMAGE_VALID` 1, `STATE` running, result `OK`, `$A003` still 3 (the exit is not a select), `$A000` 0x68 |
| Menu frame after the exit (`menu-after`) | `snapshot/b867f7c9…` | epoch 31, seq 945; pixel-exact `expected('menu')`, 23040 pixels, 0 mismatches, CRC32 `bee303ec`, frame SHA-256 `d9b6cc8e…`, byte-identical to the menu frame before the selection; cursor 0 |

The epoch advanced by one at the selection (29 to 30) and by one at the
game's exit write (30 to 31). Board state after the session: the session 6
bitstream, menu running from the host-loaded four-game library in SDRAM; the
flash copier restores the eleven-game library at the next power cycle or
KEY0. COM7 released.

### Game library acceptance

| Criterion | Evidence | State |
|---|---|---|
| Library load with zero mismatches for every slot and the catalogue; `host library status` matches | session 2 `library-load/53678d3c…`, `library-status/db747176…` (and session 1 `library-load/b6823421…`) | proven |
| Menu frame pixel-exact after a host library load | `snapshot/ba40d056…`, CRC32 `c3753fdc` | proven |
| Selection of a loaded slot through the host-injected joypad path (`host input`) starts that game | `snapshot/55c55e6b…` (cursor), `library-status/c05069ef…` (swap `OK` index 1), and the slot 0 and slot 2 swaps | proven |
| Started game title frame pixel-exact | `snapshot/72199545…`, CRC32 `4a3bad02` (Springtrail, the accepted reference game; stackdrop and v05 frames retained without a reference) | proven |
| Return to the menu with a pixel-exact menu frame | host return `write/9ab81d26…` then `snapshot/58a8f84a…`, and the final return `snapshot/6770ea06…` | proven through the host return |
| A game's own exit-register write returns to the menu with a pixel-exact menu frame and the epoch advanced | session 7 `snapshot/d2747973…` (`EXIT DEMO` running, epoch 30, frame equal to the independent reference), Start `input/bdb5446b…`, then `status/daec2992…` and `library-status/011d3a65…` (`PROFILE` 2 running without host `RUN`, result `OK`, index 3) and `snapshot/b867f7c9…` (menu, epoch 31, CRC32 `bee303ec`) | proven, no hands at the board |
| Physical KEY1 hold returns to the menu with a pixel-exact menu frame | session 3 `snapshot/357c2afe…` (Stackdrop running, epoch 21) then the owner's 0.5 s hold and `snapshot/b3700193…` (menu, epoch 22, result `OK`, CRC32 `c3753fdc`); earlier presses `snapshot/15d571db…` | proven, owner present |

## Flash-resident boot and SDRAM sweep sessions

Sessions 4 and 5, both owner-authorized, first wrote the MAX 10 configuration
flash on this board on 2026-09-16 with `fpga program --pof`, following the
[flash programming procedure](#flash-programming-procedure), and proved that
the board powers up into the menu from the flash-resident library with no PC
attached. The full 64 MiB `host sdram-test --full` sweep ran afterwards on the
flash-booted design. Menu frames are compared with
[`reference.py`](../../src/dv/menu/reference.py) against the catalogue bytes
that `host library status` retains, as in the
[game library sessions](#game-library-sessions). The
[acceptance table](#flash-and-sweep-acceptance) maps each criterion to its
record; the concise records (fit, dry-run, program, status, library status,
snapshot and compare results, sweep provenance) are retained with a provenance
note and linked from the closing PR.

Six flash writes have been made on this board: sessions 4, 5, 6, 8, 9 and 10.
The current flash-resident image is
[session 10](#session-10-reflash-with-the-composite-menu): `v05-board` build
id `bcb23cdf8d544047900af649feb131e7`, wire build id `e731b1fe…`, `.pof`
SHA-256 `589b99f1…`, packed `catalogue.bin` SHA-256 `f8425a03…`, eleven games
with their taglines and the composite menu. The images of sessions 4 to 9 are
history; each earlier record names the image it was taken on.

Authorization. Every earlier board session was volatile `.sof` only. In the
morning of 2026-09-16 the owner authorized both parts: "I authorize the flash
programming session, and if needed a four-hour SDRAM sweep — that's fine",
then, after the staged `.pof` and its dry run were shown, gave the explicit go
for the write ("yes and yes"). In the evening the owner, present at the board,
authorized a second flash write with the fitted ten-game library and
power-cycled the board after each write.

### Session 4: first flash write and power-up to the menu

- Git commit: `main` `862c2051929c4eed5ab40a5a07145c4c5075f2dd`; the flash
  library packed into the image is the three-game registry set (Springtrail
  slot 0 `8b564649`, Stackdrop slot 1 `619fa99f`, V05 slot 2 `718b0dcb`, menu
  at index 16 profile 2 `ec9c63fe`), `library.hex` SHA-256 `3a9b04d3…`,
  packed `catalogue.bin` SHA-256 `7e1d0aad…`.
- Fit: `v05-board` attempt `fcaa7349c241` (tag `694-fit`), status `PASS`,
  05:30 to 05:33 UTC, build id `2a9a70b4bedaeea2877af6c52dafe527`, wire build
  id `27e5af2dc5f67a87a2eedabeb4709a2a` reported by every host record;
  configuration mode `Single Comp Image`, `.pof` SHA-256
  `5131503ded3daf242320e41b70cf3674ffcfa8d8b82c30d4d31d4117f223163e`, user
  range matched, CFM0 used 367,699 of 688,128 bytes; unconstrained clocks: the
  On-Chip Flash IP sense-enable strobe only, ignored constraints none, worst
  slack 0.148 ns (fast-corner hold on `clk_reference`).
- Quartus version: Prime 25.1std.0 Build 1129 SC Lite Edition, for fit and
  programmer.
- Dry run: `fpga-program/b7bbf7e13a62` (tag `694-program-dryrun`), `PASS`,
  `dry-run.log` line `quartus_pgm -c <cable> -m jtag -o pvb;<pof>`, no JTAG
  access.
- Flash programming: `fpga-program/50fffc44e68d` (tag `694-program`),
  `quartus_pgm -c 1 -m jtag -o pvb;<pof>` against the one `USB-Blaster [USB-1]`
  chain with `10M50DA(.|ES)/10M50DC` (IDCODE `031050DD`), "Quartus Prime
  Programmer was successful. 0 errors, 0 warnings", processing 05:42:01 to
  05:42:48 UTC, `isp_seconds` 47.219 for program, verify and blank-check;
  `pof_sha256` equal to the fit's. The flash content changed: this was the
  first CFM write on this board.
- Power cycle: the owner power-cycled the board with the UART adapter
  disconnected and no host attached, and reported the menu on the monitor.
  That report is the owner's observation; the records below are the UART
  readback after the adapter was reconnected.
- Wiring: the documented UART and JTAG connections above; nothing was rewired.

| Step | Record (tag `694-boot`) | Result |
|---|---|---|
| `host status` after reconnecting, 05:59 UTC | `status/12042b21eeb64c71b8cca70ba64055f1` | endpoint build id `27e5af2d…` (the byte-reversed fit build id); `IMAGE_VALID` 1, `PROFILE` 2, `STATE` running, `INPUT` 0 |
| `host library status` | `library-status/d8cb43fcad654bdab206f3a12ce8c95b` | `LIBRARY_STATUS` `$A000` 0x68: `window_ready`, `sdram_ready`, `flash_boot`; result `OK`; catalogue read from SDRAM SHA-256 `7e1d0aad…`, byte-identical to the fit's packed catalogue (slots 0 to 2 and the menu at 16 with the CRC32s above) |
| Menu frame | `snapshot/b56d974a70a54df0b790f2e0c48116d1` | epoch 1 (the boot copier's single reset), seq 60809; pixel-exact `expected('menu')` for that catalogue: 23040 pixels, 0 mismatches, CRC32 `03f6afad`, frame SHA-256 `c254127c2af3a7ddc7fe713e6ba3c6a12ace147b0c62fd4a6321db314370d069`; cursor 0 |

Board state after the session: flash holds the three-game library image,
menu running from the SDRAM copy the boot copier made.

### Session 5: second flash write with the ten-game library

The owner was present. This write replaced the session 4 image with the
`v05-board` fit that carries the ten-game flash library; its purpose was the
MBC1 board proof, and it repeated the flash-boot proof on the new image.

- Git commit: the fit was built at `3ab8f2066c92f4646daeb450f81b79b8c6c88063`
  on the branch squashed into `main` as `b2f8169`; the program and host records
  below were taken from the same clone at that branch's final head
  `894059ceb9654d52d598d58b67dc8e6129178c36` (host-tool and documentation
  commits after the fit; no `src/` change). `library.hex` SHA-256 `7e1da81c…`, packed
  `catalogue.bin` SHA-256 `1d274b38…`, ten games in slots 0 to 9 and the menu
  at 16.
- Fit: `v05-board` attempt `98d391b31e04` (tag `712r-fit`), status `PASS`,
  11:09 to 11:14 UTC, build id `616f1184903b78558b6f449fef352e03`, wire build
  id `032e35ef9f446f8b55783b9084116f61` reported by every host record;
  `Single Comp Image`, `.pof` SHA-256
  `b34d39a67367d83e1e63c7c17b390bde98d0d3ffa4843c865bf5bd4a34b9c50d`, user
  range matched, CFM0 used 370,683 of 688,128 bytes; unconstrained clocks: the
  flash IP strobe only, ignored constraints none, worst slack 0.049 ns
  (fast-corner hold on the system PLL clock).
- Quartus version: Prime 25.1std.0 Build 1129 SC Lite Edition.
- Flash programming: `fpga-program/f6e628cacddf` (tag `712r-program`), the
  same command and chain, `PASS`, `device_state` `changed`, `isp_seconds`
  47.562, `pof_sha256` equal to the fit's; about 11:37 UTC. The flash content
  changed from the session 4 image to this one.
- Power cycle: the owner power-cycled the board and reported "menu is up".
  The records do not state whether the UART adapter was disconnected during
  this power cycle; the no-PC power-up proof rests on session 4.

| Step | Record | Result |
|---|---|---|
| `host status`, 11:45 UTC | `712-board-status`, `status/58ee6250cbf04ad2b133f94ae5294a67` | endpoint build id `032e35ef…` equals the program record's `wire_build_id`; `IMAGE_VALID` 1, `PROFILE` 2, running |
| `host library status` | `712-board-libstatus`, `library-status/af9a82cfed9f4ce485a866b83c1e7fa3` | `$A000` 0x68: `window_ready`, `sdram_ready`, `flash_boot`; result `OK`; catalogue SHA-256 `1d274b38…`, byte-identical to the fit's packed catalogue; ten titles in slots 0 to 9 |
| Menu frame | `712-board-menu`, `snapshot/53c2483c34b048dfb9ca365e8d270888` | epoch 1, seq 29840; pixel-exact `expected('menu')` for that catalogue: 23040 pixels, 0 mismatches, CRC32 `f75484e7`, frame SHA-256 `9bda2c43…`; cursor 0 |

The MBC1 selection and gameplay frames that followed in this session belong to
the [MBC1 board proof](rtl/cartridge/MAS_loader_profile.md#verification), not
to this record. Board state after the session: flash holds the ten-game
library image.

### Session 6: flash reconfiguration restores the library without a power cycle

After the host library loads and the full sweep had overwritten the SDRAM, the
board returned to the flash-resident menu twice without a power cycle, on the
eleven-game `v05-board` fit of the PostBot slice (attempt `d3352b4ff0fb`, tag
`738-fit`, build id `2f671a6f2216860496e024e2954b712b`, wire build id
`2b714b95e224e096048616226f1a672f`, `.pof` SHA-256 `36ba5d0f…`, CFM0 used
369,711 of 688,128 bytes, packed `catalogue.bin` SHA-256 `b4b5b3f7…`). Records
from 18:42 to 18:51 UTC; the owner was present.

| Step | Record | Result |
|---|---|---|
| Flash programming over JTAG, `pvb` | `738-program`, `fpga-program/13fa692a5b8d` | `PASS`, `isp_seconds` 49.313, `device_state` changed; the MAX 10 reconfigured from CFM0 at the end of programming with no power cycle |
| `host status`, `host library status` after programming | `738-status-after-program`, `status/fe26b95b…`; `738-board-libstatus`, `library-status/e8c2da6e…` | wire build id `2b714b95…` equals the program record's; `PROFILE` 2, running; `$A000` 0x68 with `flash_boot`, result `OK`, twelve valid entries (slots 0 to 10 and the menu), catalogue SHA-256 `b4b5b3f7…` equal to the fit's |
| Menu frame | `738-board-menu`, `snapshot/e16d8d5c…` | epoch 1; pixel-exact, 23040 pixels, 0 mismatches, CRC32 `c625db9f` |
| Owner pressed and released KEY0 | [KEY0 board reset](#key0-board-reset) records | the boot copier ran again: epoch back to 1, selection cleared, `flash_boot` set, menu frame pixel-exact with the same CRC32 `c625db9f` |

Both paths ran the boot copier again: the library came back from flash with
the same catalogue and the same menu frame as at power-up.

### KEY0 board reset

The owner pressed and released KEY0 (`PIN_B8`, `board_reset_n`, active low)
twice while root read the board over COM7. Image: the session 6 flash-resident
eleven-game fit, wire build id `2b714b95e224e096048616226f1a672f`, unchanged
throughout; no reprogramming. Records 18:50 to 18:52 UTC on 2026-09-16 under
tags `512-before`, `512-after1` and `512-after2` (each with `-lib` and `-snap`
tags for the library status and snapshot). The dot counter runs at 4,194,304
dots per second, so a dot value dates the last reset.

Two facts differ from the issue text that requested this record. The board was
running the menu, not paused at input 0: the flash-boot design starts the menu
on every reset, so "paused at input 0" is not a state this image rests in
(`INPUT` was 0 throughout). And the image was the flash-resident fit of the
day, not the superseded `87d5f028…` wire build the issue named, which later
qualified fits replaced; later flash writes, most recently
[session 9](#session-9-reflash-with-the-plated-list-menu), have since replaced
it in turn.

| Step | Records | Result |
|---|---|---|
| Before, 18:50 UTC | `status/60dd7a3f…`, `library-status/008b6830…`, `snapshot/0f0b4859…` | wire build id `2b714b95…`; `IMAGE_VALID` 1, `PROFILE` 2, running, `INPUT` 0; `flash_boot`, result `OK`, selected index `$A003` 10 (PostBot had been selected earlier in the session); dot 72,866,935, epoch 5, seq 1035 |
| Press and release 1; the owner saw the VGA picture go dark, then the menu return | `status/20dbb8fc…`, `library-status/07bee945…`, `snapshot/4eca1745…` (18:51 UTC) | same wire build id; `IMAGE_VALID` 1, `PROFILE` 2, running; `flash_boot` set again, `$A003` 255 (no selection), result `OK`; dot 94,917,271 (about 22.6 s since reset), epoch 1 (was 5), seq 1349; menu frame pixel-exact against the eleven-entry reference, 23040 pixels, 0 mismatches, CRC32 `c625db9f` |
| Press and release 2 | `status/dead953a…`, `library-status/d157182f…`, `snapshot/6f70855f…` (18:52 UTC) | same wire build id, running, `flash_boot`, `$A003` 255; dot 168,652,471 (about 40.2 s since reset), where 64.5 s of uninterrupted running since the previous snapshot would have read about 365 million, so the counter restarted; epoch 1 because a full reset re-initialises it; seq 2399; menu frame pixel-exact, CRC32 `c625db9f` |

Pressing KEY0 resets the whole design: the picture blanks, the boot copier
reruns from flash, the library epoch and selection clear, and the dot counter
restarts. Releasing it lets the design come back and answer with the same
build identity. Board state after: flash-resident menu running, cursor 0, no
selection. The comparison uses the same
[`reference.py`](../../src/dv/menu/reference.py) path as the other menu frames
on this page.

### Session 8: reflash with the updated V05 image

The fourth flash write. `e17a23d` changed the `v05` image's HALT loop, so the
packed library no longer matched the flash content: the reflash carries the
rebuilt V05 into CFM0 and repeats the flash-boot, menu and selection proofs on
it. The owner put root in charge of the UART and JTAG for this session and was
not at the board; no power cycle was performed and nothing was rewired.

- Git commit: the fit was taken at `e5e3491dc02fdd55efdd58bef3b6dab4103556f7`,
  the head squashed into `main` as `e17a23d`; the `src/` content is the same at
  both. Eleven games in slots 0 to 10 and the menu at 16. Slot 2 `V05 BUTTONS`
  carries the new image, CRC32 `dda78e9e` where every earlier flash image had
  `718b0dcb`; every other slot CRC32 is unchanged. `library.hex` SHA-256
  `ee398355…`, packed `catalogue.bin` SHA-256 `dca33a9b…` with catalogue CRC32
  `e7fdbc26`, 106,752 defined words from the
  [registry](../../src/fpga/de10_lite/library.json).
- Fit: `v05-board` attempt `82be085a97fd` (tag `764-fit`), status `PASS`,
  22:43:58 to 22:48:03 UTC on 2026-09-16 (01:43 to 01:48 board clock, UTC+3, on
  2026-09-17), build id `39ded89fa8f15f25b89ebdd8c6264c67`, wire build id
  `674c26c6d8bd9eb8255ff1a89fd8de39` reported by every host record;
  configuration mode `Single Comp Image`, `UFM blocks : 1 / 1`, `.pof` SHA-256
  `e6d86943df5fb6856d11925945db8bee2621a4816f176c75dd86368cd57970ad`, user
  range matched, CFM0 used 369,933 of 688,128 bytes; unconstrained clocks: the
  On-Chip Flash IP sense-enable strobe only, ignored constraints none, worst
  slack 0.056 ns (fast-corner hold on the system PLL clock). 12,852 of 49,760
  logic elements, 1,056,616 memory bits, 2 PLLs.
- Quartus version: Prime 25.1std.0 Build 1129 SC Lite Edition, for fit and
  programmer.
- Flash programming: `fpga-program/77d8f6afade8` (tag `764-program`),
  `quartus_pgm -c 1 -m jtag -o pvb;<pof>` against the one `USB-Blaster [USB-1]`
  chain with `10M50DA(.|ES)/10M50DC` (IDCODE `031050DD`), "Quartus Prime
  Programmer was successful. 0 errors, 0 warnings", processing 01:58:55 to
  01:59:43 board clock, `isp_seconds` 48.25, `device_state` `changed`;
  `pof_sha256` equal to the fit's.
- Wiring: the documented UART and JTAG connections above.

Host records under tags `764-status-after-program` and `764-board-*`,
transaction stamps 22:59:50 to 23:01:48 UTC on 2026-09-16 (01:59:50 to 02:01:48
board clock). Menu frames are compared with
[`reference.py`](../../src/dv/menu/reference.py) against the catalogue bytes of
the `764-board-libstatus` record, as in the other menu frames on this page. The
dot counter runs at 4,194,304 dots per second, so the dot differences below are
elapsed board time.

| Step | Record | Result |
|---|---|---|
| `host status` about 7 s after programming ended | `764-status-after-program`, `status/0454c923…` | endpoint build id `674c26c6…` equals the program record's `wire_build_id`, so the MAX 10 reconfigured from CFM0 with no power cycle, as in session 6; `IMAGE_VALID` 1, `PROFILE` 2, `STATE` running, `INPUT` 0 |
| `host status`, `host library status` | `764-board-status`, `status/610d4f66…`; `764-board-libstatus`, `library-status/1c71f744…` | same wire build id, `PROFILE` 2, running; `$A000` 0x68: `window_ready`, `sdram_ready`, `flash_boot`; result `OK`, `$A003` 255 (no selection); catalogue read from SDRAM SHA-256 `dca33a9b…`, byte-identical to the fit's packed catalogue; twelve valid entries — slots 0 to 10 with slot 2 `V05 BUTTONS` `dda78e9e` and slot 10 `POSTBOT` `7daea6a1` at 65,536 bytes, and the menu at 16 |
| Menu frame | `764-board-menu`, `snapshot/7ac40cf4…` | epoch 1, seq 1501; pixel-exact `expected('menu')` for that catalogue: 23040 pixels, 0 mismatches, CRC32 `c625db9f`, frame SHA-256 `ab21e333…`; cursor 0. The titles are unchanged, so this is the same CRC32 as the session 6 menu |
| Down, Down (`764-board-down1`, `-down2`, each `host input --mask 8` then `--mask 0`), menu frame | `input/…` under those tags, `764-board-menu2`, `snapshot/54d908b9…` | epoch 1, seq 2219; pixel-exact `expected('cursor-2')`, 23040 pixels, 0 mismatches, CRC32 `598b1545`, frame SHA-256 `bf40a8f8…` |
| A on slot 2 (`764-board-select-a`: `--mask 16`, `--mask 0`), `host status`, `host library status` | `input/385f3ca9…`, `764-board-status-v05`, `status/708721f5…`; `764-board-libstatus-v05`, `library-status/98174aba…` | the loader swapped slot 2: `PROFILE` 1, `IMAGE_VALID` 1, running, `$A000` 0x28 (`window_ready` cleared by the swap), result `OK`, `$A003` 2 |
| V05 frame | `764-board-v05-frame`, `snapshot/b00b58e2…` | epoch 2, seq 618; 5760 packed bytes, SHA-256 `bc51aaa8ca4c10ff75b9845766eb05094866a150a9707fc0aaf3ae966d041d3f` |
| A pressed and released 2.05 s apart (`764-board-v05-a`, `-v05-a-rel`), frame 2.89 s after the release | `764-board-v05-frame2`, `snapshot/…` | epoch 2, seq 1093; SHA-256 `bc51aaa8…`, equal to the frame before the press: V05 lights its map tiles only while the button is held, so a frame read after the release shows no change |
| `host library return --wait` | `764-board-return`, `library-return/cf236d0c…` | `PROFILE` 1 running before, `PROFILE` 2 running after, settled; `$A000` 0x28, `$A003` 2, result `OK` |
| Menu frame after the return | `764-board-menu-after`, `snapshot/916d8e09…` | epoch 3, seq 175; pixel-exact `expected('menu')`, 23040 pixels, 0 mismatches, CRC32 `c625db9f`, frame SHA-256 `ab21e333…`, byte-identical to the menu frame before the selection; cursor 0 |

A second run held the button across the snapshot, which the first run did not.
Down, Down and A again (`764-board-hold-down1`, `-down2`, `-select`) started
V05: `764-board-hold-status`, `status/…`, `PROFILE` 1 running. Its base frame
`764-board-hold-base`, `snapshot/e3d64d32…` (epoch 4, seq 583) has SHA-256
`bc51aaa8…`, the first run's frame. A was then pressed (`764-board-hold-a`,
`--mask 16`) and left held; the frame read 2.97 s later
(`764-board-hold-held`, `snapshot/5e73e839…`, epoch 4, seq 963) has SHA-256
`11ef63e3ecf1e906f6493e7a66cb79514490c499b27bccdb6a3840a9ddecc7a5` and differs
from the base. A was released 6.35 s after the press (`764-board-hold-a-rel`,
`--mask 0`) and the frame read 2.45 s after that (`764-board-hold-released`,
`snapshot/c6793a5b…`, epoch 4, seq 1311) is SHA-256 `bc51aaa8…` again, equal to
the base. `764-board-hold-return`, `library-return/…` put the menu back:
`PROFILE` 2 running, `$A003` 2, settled. The rebuilt V05 therefore answers the
joypad on hardware, and the change is confined to the interval the button is
held.

This session repeated the flash-boot, menu and return criteria of the
[acceptance table](#flash-and-sweep-acceptance) on the image of the day; it
adds no criterion. Board state after the session: flash held this eleven-game
image, menu running from the SDRAM copy the boot copier made, COM7 released.
[Session 9](#session-9-reflash-with-the-plated-list-menu) has since replaced
that image.

### Session 9: reflash with the plated-list menu

The fifth flash write. `9f90b9d` redrew the menu as the plated list with the
nudged arrow, so the flash content no longer matched the packed library: the
reflash carries the new menu image into CFM0 and repeats the flash-boot, menu,
selection and return proofs on it. Root drove the UART and JTAG under the
owner's standing authorization; no power cycle was performed and nothing was
rewired.

- Git commit: the fit was taken at `70631903bbe92ccf0e9303048e256a812833c3c4`,
  the head squashed into `main` as `9f90b9d`. Eleven games in slots 0 to 10 and
  the menu at 16. The menu image carries the plated list, CRC32 `c1981bd9`
  where the session 8 image had `a5d8a00f`; every game slot CRC32 is unchanged,
  including slot 2 `V05 BUTTONS` `dda78e9e`. `library.hex` SHA-256
  `037e485b…`, packed `catalogue.bin` SHA-256 `696868ab…` with catalogue CRC32
  `c7ba55dc`, 106,752 defined words from the
  [registry](../../src/fpga/de10_lite/library.json) (tag `780-library`, attempt
  `ebfa7bcc4043`).
- Fit: `v05-board` attempt `4a7cb2ecd913` (tag `780-fit`), status `PASS`,
  09:29:26 to 09:32:30 UTC on 2026-09-17 (12:29 to 12:32 board clock, UTC+3),
  build id `168cc4f3f65e7f37d87dbaee30ca76f4`, wire build id
  `f476ca30eeba7dd8377f5ef6f3c48c16` reported by every host record;
  configuration mode `Single Comp Image`, `UFM blocks : 1 / 1`, `.pof` SHA-256
  `4d258b6cec89fd4866e5ea04a73ccaa0ca9124f472296868f6600a900ca7b774`, user
  range matched, CFM0 used 369,600 of 688,128 bytes; unconstrained clocks: the
  On-Chip Flash IP sense-enable strobe only, ignored constraints none, worst
  slack 0.055 ns (fast-corner hold on the system PLL clock); the SDRAM clock's
  worst hold slack is 18.908 ns. 12,891 of 49,760 logic elements, 1,056,616
  memory bits, 2 PLLs.
- Quartus version: Prime 25.1std.0 Build 1129 SC Lite Edition, for fit and
  programmer.
- Flash programming: `fpga-program/5a3a39b9d5c7` (tag `780-program`),
  `quartus_pgm -c 1 -m jtag -o pvb;<pof>` against the one `USB-Blaster [USB-0]`
  chain with `10M50DA(.|ES)/10M50DC` (IDCODE `031050DD`), "Quartus Prime
  Programmer was successful. 0 errors, 0 warnings", processing 12:33:11 to
  12:33:54 board clock, `isp_seconds` 43.359, `device_state` `changed`;
  `pof_sha256` equal to the fit's.
- Wiring: the documented UART and JTAG connections above.

Host records under tags `780-board-*`, transaction stamps 09:34:32 to 09:35:10
UTC on 2026-09-17 (12:34:32 to 12:35:10 board clock). Menu frames are compared
with [`reference.py`](../../src/dv/menu/reference.py) against the catalogue
bytes of the `780-board-libstatus` record, as in the other menu frames on this
page, and against both
[nudge phases](sw/menu/SPEC.md#cursor-object); the comparison records
report the matching phase and the mismatch count for each. The dot counter runs
at 4,194,304 dots per second, so the dot differences below are elapsed board
time.

| Step | Record | Result |
|---|---|---|
| `host status` about 38 s after programming ended | `780-board-status`, `status/d8aac40e…` | endpoint build id `f476ca30…` equals the program record's `wire_build_id`, so the MAX 10 reconfigured from CFM0 with no power cycle, as in sessions 6 and 8; `IMAGE_VALID` 1, `PROFILE` 2, `STATE` running, `INPUT` 0 |
| `host library status` | `780-board-libstatus`, `library-status/42bd3948…` | `$A000` 0x68: `window_ready`, `sdram_ready`, `flash_boot`; result `OK`, `$A003` 255 (no selection); catalogue read from SDRAM SHA-256 `696868ab…`, byte-identical to the fit's packed catalogue; twelve valid entries — slots 0 to 10 with slot 2 `V05 BUTTONS` `dda78e9e` and slot 10 `POSTBOT` `7daea6a1` at 65,536 bytes, and the menu at 16 with the new `c1981bd9` |
| Menu frame | `780-board-menu1`, `snapshot/16146696…` | epoch 1, seq 2574; pixel-exact `expected('phase-0')` for that catalogue: 23040 pixels, 0 mismatches, CRC32 `c0e7fe66`, frame SHA-256 `62ca6439…`; cursor 0 |
| Two more menu frames, 3.38 s and 3.32 s later, with no input between them | `780-board-menu2`, `snapshot/7708005a…`; `780-board-menu3`, `snapshot/fe7f017d…` | epoch 1, seq 2776 and 2974; both pixel-exact `expected('phase-1')`, 23040 pixels, 0 mismatches, CRC32 `bffcb7ee`, frame SHA-256 `0ff3278d…`. Each frame differs from the other phase's reference by 14 pixels, the nudged arrow, so the idle menu animates on hardware |
| Down, Down (`780-board-down1`, `-down2`, each `host input --mask 8` then `--mask 0`), menu frame | `input/…` under those tags, `780-board-cursor2`, `snapshot/d6cf2086…` | epoch 1, seq 3647; pixel-exact `expected('cursor-2')` in phase 1, 23040 pixels, 0 mismatches, CRC32 `c1e03a85`, frame SHA-256 `20ae0bfd…`; 14 pixels from the phase 0 reference |
| A on slot 2 (`780-board-select-a`: `--mask 16`, `--mask 0`), `host status` | `input/a59363d6…`, `780-board-status-v05`, `status/586356cc…` | the loader swapped slot 2: `PROFILE` 1, `IMAGE_VALID` 1, running, `INPUT` 0 |
| `host library return --wait` | `780-board-return`, `library-return/d7ba1a34…` | `PROFILE` 1 running before, `PROFILE` 2 running after, settled; `$A000` 0x28 (`window_ready` cleared by the swap), `$A003` 2, result `OK` |
| Menu frame after the return | `780-board-menu-after`, `snapshot/82dd1bea…` | epoch 3, seq 174; pixel-exact `expected('phase-0')`, 23040 pixels, 0 mismatches, CRC32 `c0e7fe66`, frame SHA-256 `62ca6439…`, byte-identical to the first menu frame of the session; cursor 0 |

This session repeats the flash-boot, menu, selection and return criteria of the
[acceptance table](#flash-and-sweep-acceptance) on the new image and adds the
nudge phase to the menu comparison; it adds no criterion. Board state after the
session: flash holds this eleven-game image with the plated-list menu, menu
running from the SDRAM copy the boot copier made, COM7 released.
[Session 10](#session-10-reflash-with-the-composite-menu) has since replaced
that image.

### Session 10: reflash with the composite menu

The sixth flash write. The menu became the
[composite menu](sw/menu/SPEC.md): the boot splash, the grey plates, the
star field, the information footer with each game's tagline, the scroll ramp
onto the last slot and the press-A pulse, so the flash content no longer
matched the packed library. The reflash carries the new menu image and the
tagline table into CFM0 and reads every
[frame class](sw/menu/SPEC.md#verification) back from the board, pixel-exact
against [`reference.py`](../../src/dv/menu/reference.py). Root drove the UART
and JTAG under the owner's standing authorization; no power cycle was
performed and nothing was rewired.

- Git commit: the fit was taken at `970afc6a` (`main`), whose `v05-board`
  sources, constraints, software and registry are byte-identical to the head
  this record was delivered from; the delivering change added verification
  and documentation only. Eleven games in slots 0 to 10 and the menu at 16.
  The menu image carries the composite menu, CRC32 `cda473fb` where the
  session 9 image had `c1981bd9`; every game slot CRC32 is unchanged,
  including slot 2 `V05 BUTTONS` `dda78e9e`. The tagline table is populated
  for the first time: every game declares one
  ([registry](../../src/fpga/de10_lite/library.json) or its software target).
  `library.hex` SHA-256 `296cf0ea…`, `library.dat` SHA-256 `12aad9ef…`,
  packed `catalogue.bin` SHA-256
  `f8425a03ad886987b0e4e5d0fa3e17a83e64bbced64be8a72555d417f96af09f` with
  catalogue CRC32 `663d98aa`, 106,752 defined words. An independent offline
  pack of the same registry on Linux (tag `p794-library`) produced the same
  three digests.
- Fit: `v05-board` attempt `626baa1e12a9` (tag `794-fit`), status `PASS`,
  05:30:50 to 05:35:00 UTC on 2026-09-18 (08:30 to 08:35 board clock, UTC+3),
  build id `bcb23cdf8d544047900af649feb131e7`, wire build id
  `e731b1fe49f60a904740548ddf3cb2bc` reported by every host record;
  configuration mode `Single Comp Image`, `UFM blocks : 1 / 1`, `.pof` SHA-256
  `589b99f15d6ca8245413a3fb01bd04a9759149504e473a509af72dfbc36ca4cb`, `.sof`
  SHA-256 `60c1c0b6…`, user range matched, CFM0 used 370,784 of 688,128
  bytes; the classified flash IP diagnostic 10036 only, ignored constraints
  none, worst hold slack 0.015 ns (system PLL clock, fast model), worst setup
  slack 4.1 ns. 12,880 of 49,760 logic elements, 1,056,616 of 1,677,312
  memory bits.
- Quartus version: Prime 25.1std.0 Build 1129 SC Lite Edition, for fit and
  programmer.
- Flash programming: dry run `fpga-program/2e13a4deaf1e` (tag
  `794-program-dry`), then `fpga-program/5f3175934aa6` (tag `794-program`),
  `quartus_pgm -c 1 -m jtag -o pvb;<pof>` against the one
  `USB-Blaster [USB-0]` chain with `10M50DA(.|ES)/10M50DC` (IDCODE
  `031050DD`), "Quartus Prime Programmer was successful. 0 errors, 0
  warnings", processing 08:59:22 to 09:00:04 board clock, `isp_seconds`
  43.438, `device_state` `changed`; `pof_sha256` equal to the fit's.
- Wiring: the documented UART and JTAG connections above.

Host records under tags `794-board-*` and `794-board3`, transaction stamps
06:00:21 to 06:19:40 UTC on 2026-09-18 (09:00 to 09:19 board clock). The
board has no joypad and a UART round trip is longer than the one-frame
classes last, so the frame proof holds the core host-paused and advances it
one frame at a time: [`board_menu.py`](../../src/dv/menu/board_menu.py)
sends `RESET` (the core comes back `PAUSED`), `RUN_DOTS` of one frame
(70,224 dots), `INPUT` for the edge the next VBlank samples, and `SNAPSHOT`
for the frame that completed, then compares each capture through
[`board_compare.py`](../../src/dv/menu/board_compare.py) with the catalogue
read from the board's own SDRAM. A core reset keeps the loader's selected
index, so the splash, which the menu arms only while `$A003` is still `$FF`,
runs first and the refused and accepted selects come last. Every capture
retains its packed frame, the frame, reference and diff pictures, the
comparison record with CRC32 and SHA-256, and the snapshot's epoch, sequence
and dot; the dot counter runs at 4,194,304 dots per second, and every step
advanced the dot by exactly 70,224 and the sequence by one. The passing run,
`794-board3`, made 85 captures in 115.4 s of wall time, 06:17:20 to 06:19:14
UTC, every one pixel-exact.

| Step | Record | Result |
|---|---|---|
| `host status` about 21 s after programming ended | `794-board-status`, `status/09d57344…` | endpoint build id `e731b1fe…` equals the program record's `wire_build_id`, so the MAX 10 reconfigured from CFM0 without a power cycle, as in sessions 6, 8 and 9; `IMAGE_VALID` 1, `PROFILE` 2, `STATE` running, `INPUT` 0 |
| `host library status` | `794-board-libstatus`, `library-status/99ff28f0…` | `$A000` 0x68: `window_ready`, `sdram_ready`, `flash_boot`; result `OK`, `$A003` 255 (no selection); catalogue read from SDRAM SHA-256 `f8425a03…`, byte-identical to the fit's packed catalogue; twelve valid entries with their taglines, slot 2 `V05 BUTTONS` `dda78e9e`, slot 10 `POSTBOT` `7daea6a1` at 65,536 bytes, the menu at 16 with `cda473fb` |
| Boot splash: `RESET`, then one frame a step | captures `00-splash-first` to `17-splash-16`, epoch 4 | the first complete frame arrived after 6 frames with the LCD off. Sequences 0, 1 and 2 are all the BGP `$00` frame (CRC32 `b15161f6`): the observer publishes the frame that ends at the VBlank of the menu's first loop iteration, one frame before displayed frame 0, and the two-frame fade hold follows it. From there the 17 displayed frames match `splash-0` to `splash-16` in order, one a step: `$40` (`3afb972e`), `$90` (`86a6fa5c`), `$E4` (`15b07131`), then the nine slide steps SCY 16 to 144 (`0ca82437`, `99e7f0a5`, `c67b7d4b`, `0204f124`, `ece8d680`, `82ef4f54`, `bd413b01`, `43769591`) drawing the wrapped rows; `splash-16`, sequence 17, is the settled menu, CRC32 `b55d707f` |
| Idle, both phases: 16 frames a step | `18-idle-first`, `19-idle-phase-1`, `20-idle-phase-0` | `phase-0` at sequence 17 (`b55d707f`), `phase-1` at 33 (nudged arrow, star twinkle, ink press-A badge; `a79e1c8e`), `phase-0` again at 49 (`b55d707f`) |
| Down, Down: staged and settled footer | `21-move-1-from-0-f0` … `24-move-2-from-1-f1` | each move shows the pointer on the new slot with the new slot's upper footer row and the old slot's lower row for one frame (`cb345b5a`, `0b1e2fda`), then the settled footer (`727eb34a`, `59acbdc9`: `DIRECT   32 KB` and the tagline `BUTTON TEST`) |
| Down to slot 14, Down onto slot 15 | `25-move-3-from-2-f0` … `53-move-15-from-14-f3` | every move pixel-exact staged and settled. The Down onto slot 11 landed on menu frame 64, a nudge-phase boundary: that frame (`eb3b95e1`) shows the pointer on slot 11 with both footer rows still describing slot 10, the [footer rule](sw/menu/SPEC.md#the-information-footer)'s twinkle-frame deferral, then `75cdfd06` staged and `b63caaa0` settled; the driver accepts a deferred row only on that boundary. The move onto slot 15 carries SCY 146 with the staged footer (`e3d06ec5`), then 148 (`6f7831f7`), 150 (`ff5552ba`) and 152 (`9b54596b`), the header leaving the top and the pointer riding its row over the plate |
| Up off slot 15 | `54-move-14-from-15-f0` … `57-move-14-from-15-f3` | SCY 150 with the staged footer (`d2868cc9`), then 148 (`4db5af4f`), 146 (`543c52d6`) and the settled 144 (`9eb63a07`) |
| Up to slot 11 | `58-move-13-from-14-f0` … `63-move-11-from-12-f1` | the empty slots' footer reads `EMPTY SLOT` with the plate's own fill on the lower row (`29ce7581`, `4bf1811a`, `a1ce3873`) |
| A on slot 11, then Up | `64-refused` (`7f574ad6`), `65-move-10-from-11-f0`, `66-move-10-from-11-f1` (`ed3c114c`); `LIBRARY_STATUS` read | result `INVALID_SLOT` index 11 with `window_ready` set; the frame shows `SLOT 11 INVALID` in place of the lower row; Up moves the pointer to slot 10 (`MBC1     64 KB`) and the message stays, staged then settled |
| Up to slot 2, A | `67-move-9-from-10-f0` … `82-move-2-from-3-f1` (message kept, `85553e79`), then the endpoint view in `result.json` | the loader swapped slot 2: result `OK` index 2, `PROFILE` 1, `IMAGE_VALID` 1, `STATE` paused, because the core was host-paused when the select committed; the driver sent `RUN` |
| V05 frame, 2 s after the game started | `83-game` | epoch 5, sequence 118; 5760 packed bytes, SHA-256 `bc51aaa8ca4c10ff75b9845766eb05094866a150a9707fc0aaf3ae966d041d3f`, equal to the session 8 and 9 frames of the unchanged image |
| `host library return --wait`, menu frame | `84-menu-after-return` | `PROFILE` 1 running before, `PROFILE` 2 running after, settled in one status read, result `OK`, `$A003` 2; the menu starts settled with no splash because `$A003` kept slot 2, cursor 0, status row blank; epoch 6, pixel-exact `phase-1`, CRC32 `a79e1c8e`, the idle phase-1 frame of the session |
| `host status`, `host library status` after the session | `794-board-status-after`, `status/92b7bd45…`; `794-board-libstatus-after`, `library-status/9a006d42…` | same wire build id, `PROFILE` 2, running, `INPUT` 0; catalogue SHA-256 `f8425a03…` unchanged, flags unchanged, result `OK`, `$A003` 2 |

Two earlier runs of the same session failed on the driver's expectations
and are retained beside the passing one. `794-board` (driver at `a8953f5`)
stopped at the third splash capture: it demanded `splash-2` at sequence 2
and did not know the observer's leading frame. `794-board2` (driver at
`27122b2`) accepted the leading frame and matched the splash, the idle
phases and the moves through slot 10, then stopped on the Down onto slot 11:
it expected the staged footer in the move's own frame and did not know the
twinkle-frame deferral. The menu behaved as its contract states in both; the
driver at `f904783` models both rules and ran the whole session.

This session proves every [frame class](sw/menu/SPEC.md#verification) of the
composite menu on the board: splash, both nudge phases, staged and settled
footer, tagline and empty-slot footer, scroll ramp on and off the last slot,
refused select with its message, select and return. Board state after the
session: flash holds this eleven-game image with the composite menu, menu
running from the SDRAM copy the boot copier made, cursor 0, `$A003` 2 so the
splash is disarmed until the next global reset, COM7 released.

### Full SDRAM sweep

`host sdram-test --full` writes the seeded pattern over the whole 64 MiB
device fifteen lines per `SDRAM_WRITE`, reads it back fifteen lines per
`SDRAM_READ` and compares every line
([storage contract](rtl/storage/MAS_sdram.md#verification)). Two runs:

| Run | Design | Record | Result |
|---|---|---|---|
| Partial (stopped) | session 4 image, wire build id `27e5af2d…` | tag `694-sweep`, `sdram-test/2895a7af46e74a218e03297a8f882593`, `PROVENANCE-partial.txt` | started 06:00 UTC right after session 4; stopped by the owner's decision at 11:36 UTC to free the board for session 5, after sequence 453,662 of about 559k transactions (about 81%, into the read-back phase); 0 mismatching lines, every logged response status 0; no `result.json` because the run did not complete |
| Full, unattended | session 5 image (the ten-game flash-boot design), wire build id `032e35ef…`, records at `894059c` | tag `712-sweep`, `sdram-test/9596bf11ae5f474fb91962b9338c53ac` | `PASS`: seed 1, start 0, length 67,108,864 bytes, `lines` 4,194,304, `mismatch_count` 0; first transaction 12:03:45 UTC, last 18:35:20 UTC, elapsed 23,494.6 s (6 h 31 m) at 115200 baud, against the about 4 h estimate |

The sweep overwrites the SDRAM library; the boot copier restores it from flash
at the next power cycle.

### Flash and sweep acceptance

| Criterion | Evidence | State |
|---|---|---|
| Recorded `.pof` programming with the measured ISP time | session 4 `fpga-program/50fffc44e68d`, `isp_seconds` 47.219 (and session 5 `fpga-program/f6e628cacddf`, 47.562) | proven |
| Power-up to the menu with the UART disconnected | session 4: owner power cycle with the adapter disconnected and no host attached, menu reported on the monitor; after reconnecting, `flash_boot` set and epoch 1 | proven, owner report for the picture, UART readback for the state |
| Pixel-exact menu frame read back afterwards | session 4 `snapshot/b56d974a…`, CRC32 `03f6afad` (and session 5 `snapshot/53c2483c…`, CRC32 `f75484e7`) | proven |
| `host sdram-test --full`: 4,194,304 lines, zero mismatches, elapsed time | `712-sweep` `sdram-test/9596bf11…`: `lines` 4,194,304, `mismatch_count` 0, `PASS`, 23,494.6 s (after the partial `694-sweep` run on the session 4 design: 0 mismatches to sequence 453,662) | proven on the session 5 design |

## Display observation

On 2026-09-13 the board owner connected a monitor to the DE10-Lite VGA output,
looked at it, and reported the picture as correct: "I see the Stackdrop
picture! score state etc.. all looks good."

Conditions at the time of the observation:

- Wire build `87d5f0280a2afad8be6b85dc601141cc`, ABI 1: the already-programmed
  build reused for that session, not the build in the run record above.
- Loaded image: the restyled Stackdrop of that day, SHA-256
  `f2a9b159743a202541dd17dedaa99ffcc7ebf6d9d7012b28f4701a0ac9aed927`, 32768
  bytes, profile `dmg-direct-v1`, built from `main` at `1b18cfc2`. That hash
  identifies the image observed, not the current build, which later source
  changes superseded. Loaded with `host load --package`, all 32768 bytes
  verified on readback, then `host reset`.
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

None. The last physical-presence item on this page, the KEY0 board reset, is
recorded [above](#key0-board-reset).
