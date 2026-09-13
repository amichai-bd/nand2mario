# Building a Game Boy on an FPGA, from a phone

*13 September 2026 · A project retrospective, not a release certificate*

I was away on reserve duty, without physical access to my PC or FPGA. Before
leaving, I had installed the ChatGPT app and connected the board and its UART
adapter. That small piece of preparation turned into a surprisingly large
experiment: could I direct agents from my phone, have them build and verify a
Game Boy-style computer at home, and eventually play its game from the same phone?

<a href="../tools/n2m/host/LIVE_VIEWER.md"><img src="../tools/n2m/host/assets/live-viewer-phone.jpg" width="300" alt="Owner-provided phone screenshot showing actual FPGA pixels, Game Boy buttons and retired input commands"></a>

This is my phone looking at the FPGA's actual framebuffer through UART. It is
not a camera pointed at a monitor. The controls below it send bounded button
presses to the same host process that reads the pixels.

## TL;DR

I set out to build something I could recognize and play: a Game Boy-compatible
system on a DE10-Lite FPGA. The name nand2mario preserves the original ambition,
but the project became a hardware platform with original games rather than a
way to distribute Mario. That choice avoided bringing commercial ROMs and copied
assets into the project. Gameplay lives in ordinary SM83 software; it is not
hardwired into the FPGA.

The unusual constraint was that all work after I left was remote, directed from
my phone while I was away on reserve duty. I used remote app sessions and SSH into the home Windows
machine. Agents worked across RTL, Python tooling, assembly, graphics,
specifications and tests. I called the orchestrator Firstmate. It assigned an
issue, gave an author a separate worktree and short branch, arranged an
independent AI review, and merged after the required evidence passed. I did not
approve every PR individually. I still chose goals and authorized changes in
scope or physical access.

The repository's dated history runs from early scaffolding on 4 September to the
phone viewer on 13 September. In between came a custom assembler and linker,
a CPU and graphics pipeline, Intel memory-model simulation, UART controls,
original games, and bounded physical tests. The useful breakthroughs were often
about verification: replacing impractically long simulation plans with short
complete harness checks plus bounded board runs, separating intended state from
actual pixels, and making failures stop cleanly.

It was not a smooth autonomous success story. A stale snapshot epoch created a
false reset alarm. Old game expectations stopped matching lives and countdown
behavior. The first hour-long viewer command was actually subject to a
five-minute supervisor limit. Restarting then encountered a stale session lock.
Those failures mattered because I could not walk over to the machine and inspect
it. Every remote claim needed an observable state and a recoverable path.

The final viewer captures a frame in roughly 1.1 seconds and normally refreshes
about every two seconds: around 0.5 frames per second, not video-rate streaming.
It is enough to see the game and try tap controls, with obvious latency. This is
scoped evidence of real software running on real hardware, not universal Game
Boy compatibility or proof of a physical monitor. My strongest lesson was that
remote hardware work needed trustworthy evidence and recoverable tooling more
than it needed a larger number of agents.

## The phone was the control room

The practical access chain mattered as much as the model. I used Termius and
Tailscale for SSH access to the home machine, going through Windows WSL into
PowerShell when necessary. I also used the Android ChatGPT remote experience
and, later, the Android Claude app connected to Claude Code remote sessions. The tools changed, but
the working directory, issue history and build records gave the work somewhere
to persist outside a chat window.

My recollection is that I started with the $200 ChatGPT plan and mostly used a
model labeled Astra for the first three or four days. I used weekly-limit resets
roughly daily for a while, then exhausted them. I bought the $200 Claude
plan, mostly used the label Fable 5.1, and installed it remotely. Those are my
recollections of the subscriptions and labels I saw, not a dated billing audit
or a mapping to current public model names. The repository can date a merge;
it cannot tell me exactly which credit reset paid for the conversation that
produced it.

That distinction is worth keeping. It is tempting to turn the story into a
comparison of two models or a claim that a fixed amount of money bought a
complete computer. I do not have a controlled experiment for either conclusion.
What I do have is a record of decisions, code, checks and corrections across
changing tools. Keeping that record in the repository made switching tools much
less disruptive than it would have been if the plan lived only in one session.

## Firstmate needed rules, not just workers

I called the orchestrator Firstmate because I wanted something closer to a
working engineering lead than a collection of independent chats. Its job was to
choose the next bounded issue, keep ownership clear and finish work already
close to delivery. An author worked in a separate Git worktree. Another agent
reviewed the current commit. A draft PR carried the finite acceptance checklist.
After checks and review, the author could merge without coming back to me for
routine approval.

The boundaries were deliberate. Permission to change a host tool was not
permission to program a board. A source implementation was not proof that it
worked physically. An old passing run could be reused only when its relevant
inputs had not changed. These rules are now written in
[AGENTS](../../AGENTS.md) and the
[agent workflow](../../.agents/skills/agent-flow/SKILL.md).

Colocating specifications and implementation was especially useful with agents.
A reviewer could compare the contract, code and test instead of relying on an
author's summary. The wiki was published through Pages; illustrated decks
explained CPU, memory, graphics and verification concepts; statistics made the
activity visible. None of those pages was supposed to replace source evidence.
A chart of merged PRs measures activity, not correctness.

There was an unexpected benefit to making the builder cross-disciplinary. It
had to know about Python environments, assemblers, simulation inputs, generated
interfaces and FPGA tools. That made it possible to ask one concrete question:
what exact inputs produced this result? It also exposed integration mistakes
that a narrow unit test missed, such as an import working in a clean process
but failing after another suite had cached a module with the same name.

## What the agents were actually building

The hardware is a DMG-oriented system: SM83 CPU, memory map, graphics, timers,
interrupts, DMA and joypad behavior. The DE10-Lite implementation uses a 25 MHz
system architecture. The change from a 50 MHz internal system clock to 25 MHz
was a timing-closure choice; it preserved the emulated 4.194304 MHz Game Boy tick.
The game was not being sped up to run at 25 MHz.
The display side includes VGA, while UART provides loading, execution controls,
input and snapshots. The
[architecture lessons](../presentations/README.md) and
[ownership map](../ownership.md) are better entry points than a wall of module
names.

The software side grew too. The repository contains a Python assembler,
linker, asset conversion and ROM build pipeline. Springtrail is an original
SM83 platformer; Stackdrop is another original game. Making the software ordinary
Game Boy code was important. A game-specific shortcut in RTL could have produced
a convincing screen without answering the question I was trying to ask.

The original Mario idea became original characters, maps and mechanics. I wanted
a project I could share without distributing commercial game content. That is a
project and distribution choice, not a claim that emulation itself is illegal.
Original software also made debugging easier: when the CPU, game and reference
model disagreed, the source for all three was available.

Third-party compatibility was a separate, narrower exercise. There is evidence
for the downloaded **Libbet and the Magic Floor v0.08**, with a pinned upstream
revision and provenance. There are also CPU test ROMs such as Mooneye's reg_f.
A test ROM is not another playable game, and a Libbet title/tutorial run does not
mean that an arbitrary cartridge will work. The
[compatibility evidence](../src/dv/integration/SPEC.md) must be read at that scope.
The first Libbet attempt stalled at an audio-register write: the programmed
bitstream predated the merged register gateway. Rebuilding and programming the
current design enabled the title, a tutorial move and a thirty-second attract
demo. That was a deployment mismatch with specific follow-up evidence, not proof
of full game completion or sound synthesis.
[The initial failure](https://github.com/amichai-bd/nand2mario/pull/382) is part of
the result, not an embarrassing record to remove.

## A dated trail of turning points

The dates below use repository merge timestamps in UTC. They do not assign exact
dates to my recollections of travel, subscriptions or model switches.

| Date (2026, UTC) | Turning point | Why it mattered |
|---|---|---|
| 4 September | [Scaffolding and early contracts](https://github.com/amichai-bd/nand2mario/pull/23) | The project acquired a place for requirements before the system was complete. |
| 5 September | [Assembler](https://github.com/amichai-bd/nand2mario/pull/112), [linker](https://github.com/amichai-bd/nand2mario/pull/117) and [assets](https://github.com/amichai-bd/nand2mario/pull/121) | Software and its build inputs became owned parts of the platform. |
| 6–7 September | [Intel memories](https://github.com/amichai-bd/nand2mario/pull/143), [25 MHz architecture](https://github.com/amichai-bd/nand2mario/pull/167) and [verification tiers](https://github.com/amichai-bd/nand2mario/pull/184) | Simulation realism and finite acceptance became explicit design constraints. |
| 9 September | [Springtrail](https://github.com/amichai-bd/nand2mario/pull/266) and [Stackdrop play evidence](https://github.com/amichai-bd/nand2mario/pull/275) | Original software made the hardware something to exercise rather than only inspect. |
| 11 September | [Libbet refit](https://github.com/amichai-bd/nand2mario/pull/387) and [tutorial/attract proof](https://github.com/amichai-bd/nand2mario/pull/389) | A specific external game exposed the difference between current RTL and the programmed image. |
| 12–13 September | [State/pixel play proof](https://github.com/amichai-bd/nand2mario/pull/517), [current host expectations](https://github.com/amichai-bd/nand2mario/pull/522) and [ten-minute run](https://github.com/amichai-bd/nand2mario/pull/525) | Assertions and measurements were rebound to the actual current software. |
| 13 September | [Phone viewer, controls and history](https://github.com/amichai-bd/nand2mario/pull/534) | The remote feedback path finally became something I could use directly. |

## Verification changed shape when it met the clock

Questa and Quartus were essential, but they answered different questions.
Questa could expose CPU retirements, bus transactions and the exact mismatch
behind a failure. Quartus and the Intel memory models mattered for the design
that would actually fit and run on the MAX 10. Neither justified treating a
long software playthrough as a cheap simulation task.

A continuous Python UART path made the actual product client usable in
simulation, alongside checked preload equivalence. An earlier investigation of
slow control calls never established a Tcl root cause; it would be misleading
to turn that history into a measured claim that Python fixed a vendor bug. The
useful result was a bounded, complete harness with observable failures.
[PR177](https://github.com/amichai-bd/nand2mario/pull/177) records that path.

The eventual approach was complementary. First exercise the complete simulation
harness at a short duration, including completion, pause, watchdog and cleanup.
Use bounded tests for the specific CPU or rendering obligation. Use physical
runs for longer execution where appropriate, with explicit authorization,
identity checks and serialized access. Preserve meaningful negative tests so
that a checker had to reject a deliberately wrong result.

For example, the later Springtrail proof compared five complete 160×144 frames:
23,040 shade values per checkpoint, rather than a few reassuring pixels. A
separate set of twenty samples measured the state and pixel paths. The corrected
warm medians were about 0.122 seconds for state acquisition, 0.138 seconds for
state acquisition plus host image construction, and 1.051 seconds for the actual snapshot path. These
are different operations, not three estimates of the same frame rate.
[PR517](https://github.com/amichai-bd/nand2mario/pull/517) records the boundaries.

The physical ten-minute run later recorded 602.522 seconds of continuous
execution and 666.019 seconds for the whole supervised operation. It checked
75 complete frames and retained the reset/full-load/readback lifecycles required
by that plan. Calling it a “ten-minute test” without the whole-process time
would have hidden setup and cleanup costs. Calling it a thirty-minute milestone
would have been false.
[PR525](https://github.com/amichai-bd/nand2mario/pull/525) keeps those distinctions.

## Three failures that improved the evidence

One apparent reset was actually a provenance mistake. The host treated a
snapshot epoch register as if it described the live reset state. The RTL exposed
capture-latched metadata instead. After reset, the first new capture could
replace a stale latch; the next observation then looked like an unexpected epoch
change. The correction was to acquire fresh metadata at a coherent paused
boundary and retain the real cross-observation epoch guard. Removing the guard
would have made the run greener and the evidence worse.

Another problem came from the game's own evolution. Endurance expectations still
assumed an older lives/timer lifecycle. The current game spent lives, counted
neutral play updates, reached OVER and required a later released Start to reset.
A route that once worked also died at a CURL enemy before reaching its intended
checkpoints. The fix was a small stimulus adjustment plus current independent
state history, not a more forgiving pixel comparison. Whole-frame expectations
had to come from reachable states; mixing whichever timer and platform pixels
happened to match would not have been an oracle.
[PR522](https://github.com/amichai-bd/nand2mario/pull/522) documents that correction.

The most visible failure happened after I had the phone page. A command that
advertised a one-hour lease used a simulation supervisor whose ceiling could
only shrink the default five-minute budget. The viewer was killed. Reusing the
same artifact tag then failed, and a stale session lock made a later startup
refuse access. A generic preflight message hid the useful cause.

The correction used the existing operational supervisor with a real 3,630-second
cap for a 3,600-second lease, bounded cleanup, and one automatically generated
tag shared by parent and worker. The live session was observed past 442 seconds,
beyond the old limit; that was evidence for the correction, not a claim that an
hour had completed. Better preflight diagnostics remained a
[separate open issue](https://github.com/amichai-bd/nand2mario/issues/536).

## A slow viewer was still a major change

The final feedback loop was straightforward in principle: capture the FPGA's
packed framebuffer through UART, encode a native PNG on the host, and serve the
latest image and status on loopback. A temporary authenticated HTTPS tunnel made
that page reachable from my phone. The browser never opened another serial
connection.

Input needed the same discipline. A finite FIFO batch is frozen, each bounded
press is executed and released, then the next full snapshot begins. Requests
that arrive during that work wait for the next batch. This prevents a key from
remaining held throughout a roughly 1.1-second frame readback. It also makes the
latency honest: a batch of input takes time before the next image can appear.

Command history became part of usability, not decoration. QUEUED means accepted;
EXECUTING means the worker started it; RETIRED means both press and release were
verified. Errors and uncertainty are not painted green. Newest-first entries let
me distinguish an old screen from a command that had not run yet. One bounded
Right request recorded a 134 ms request, about 142 ms measured hold, verified
release and continued captures in the same worker. Other user requests could
also be present, so the evidence did not attribute every visible movement to
that one command.

At about one refresh every two seconds, this is approximately 0.5 fps. It is a
useful remote view with tap controls, not a responsive handheld replacement.
It also does not establish VGA signal quality or prove what a physical monitor
shows. The [viewer guide](../tools/n2m/host/LIVE_VIEWER.md) explains the actual
interface and its limits.

## What I would carry into the next project

I would keep small issues, separate worktrees and independent review. More
workers are useful only when their ownership and inputs are clear. A reviewer
who can find a concrete mismatch is more valuable than another author producing
code against the wrong assumption.

I would keep the specification beside the implementation, and make the required
checks executable through the same entry points people actually use. Several
failures lived in the space between a helper function and the real command.
Testing the helper alone would have missed them.

Most of all, I would design recovery before relying on remote access. A status
label needs a timestamp. A successful command needs a verified release. A long
lease needs the budget the parent really selected. A failed process needs an
explanation that survives it. Those details sound mundane until the hardware is
somewhere you cannot reach.

The exciting part was not watching agents produce a large diff. It was seeing
actual pixels from a machine at home, pressing a button from my phone, and
having enough evidence to understand what happened. That was the point where
the project stopped being a collection of promises and became a tool I could use.

---

*Written with AI assistance from the owner's firsthand account and dated
repository evidence. Personal subscription, model-label and rough day-count
recollections are attributed above; technical measurements link to their
producing records. The article records the project on 13 September 2026 and does
not replace current specifications. No Hacker News submission or comment is part
of this work.*
