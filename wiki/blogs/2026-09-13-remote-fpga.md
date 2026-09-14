# Building a Game Boy with AI agents

*Hardware, software, verification and delivery, directed from a phone at the far
end of a serial cable · Amichai Ben-David · Evidence through 14 September 2026*

I am a chip design engineer at NVIDIA, previously at Intel. Earlier this month I
was away on reserve duty with no physical access to my desk. Before leaving I had
plugged a Terasic DE10-Lite into the wall, hung a UART adapter off it, and
installed a chat app on my phone. Over the following ten days AI agents built, on
that board, an original-DMG-compatible Game Boy: an SM83 CPU, the memory map, the
PPU, DMA, timers, interrupts and joypad, a VGA display path, a UART control
channel, an [assembler and linker](#software-stack), two original games, and a
launcher that loads any of them and hands you an on-screen pad.

It is not an emulator. The CPU, PPU, memory, DMA, timers, interrupts, joypad and
the VGA output are SystemVerilog, synthesized by Quartus and placed and routed
onto the MAX 10 device on that board. The games execute as SM83 machine code on
logic, not on an interpreter. What runs on a PC is the toolchain that builds the
ROMs, the simulator that checks the hardware, and the host tools that talk to the
board down a serial cable.

<a href="../tools/n2m/host/LIVE_VIEWER.md"><img src="../tools/n2m/host/assets/live-viewer-phone.jpg" width="300" alt="Phone browser showing pixels read back from the FPGA, a row of Game Boy tap buttons, and a queued/executing/retired command list beneath them"></a>

*My phone, showing pixels the board returned over UART. Not a photograph of a
monitor, and not evidence that a monitor shows anything: these are framebuffer
bytes the board sent back, read on a phone a long way from it.*

The shape of it, before anything else. First commit 4 September 2026; eleven
active dates through the 14th. My own ten days away sit inside that eleven-date
span, which is why the two counts differ. The repository's
[frozen snapshot](../project-statistics.md) is the source for those dates, and
that page is explicit that its other totals measure size and activity, not
correctness.

This is a retrospective on the whole project: what the hardware is, what the
software is, how the work was directed and delivered, how any of it was checked,
and which few things a person still had to do. One argument runs through all of
it, because it turned out to be the expensive part. Getting the work produced was
the easy half. Establishing that the work was actually right consumed the
judgement. Two of the games here were written by strangers, run on this hardware,
and never draw a single pixel — and the most useful thing in this project was
being able to prove, from counted instructions alone, that this was not a
defect. No test we could have written would have found it.

## What got built

<a id="the-project"></a>nand2mario is an original-DMG-compatible Game Boy
implemented in SystemVerilog for the DE10-Lite, with VGA video, UART loading and
control, an original SM83 software toolchain and original games. It targets the
monochrome DMG family under the [project charter](../src/project-charter.md): a
32 KiB mapperless profile, cartridge type `0x00`, no cartridge RAM, and silent
output — the audio registers are served so the CPU never faults, but nothing is
powered and nothing is synthesized. Gameplay stays in software; the FPGA
implements the platform, not the game. The [README](../../README.md) is the entry
point for the repository, and the [ownership map](../ownership.md) says which
document owns which contract.

The device is a `10M50DAF484C7G` MAX 10 on a Terasic DE10-Lite. The design takes
its reference from the onboard 50 MHz oscillator on `PIN_P11` and derives two
clocks from it in separate PLLs. It drives twelve VGA colour pins plus hsync on
`PIN_N3` and vsync on `PIN_N1`, receives UART on `PIN_AB5` and transmits on
`PIN_AB6` at 8 mA drive, and takes its board reset from the Schmitt-trigger KEY0
input on `PIN_B8`. Unused package pins are reserved as tri-stated inputs. The
composed memory inventory is 20 logical stores across 111 M9K blocks and 761,704
bits. An accepted FPGA build must produce map, fit, assembler and timing reports
and a nonempty SOF, and its setup, hold and minimum-pulse-width slacks must be
finite, nonnegative and zero-TNS at all three corners — Slow 1200 mV 85 °C, Slow
1200 mV 0 °C and Fast 1200 mV 0 °C. Those are fit and static-timing facts about a
real device. They are also the reason a whole class of software shortcut was
unavailable throughout.

None of that makes it a Game Boy. It is an FPGA implementation of a DMG-family
system, and the [charter](../src/project-charter.md) declines to claim exact
silicon identity or universal cartridge compatibility. What each release runs is
stated there, and it is our own 32 KiB mapperless images plus whatever else
happens to fit that profile.

The emulated machine is the ordinary one. A frame is 154 lines of 456 dots —
70,224 dots, nominally 16.74270630 ms, about 59.7275 Hz. The visible area is 160
by 144, which is 23,040 pixels, and a complete ROM image is exactly 32,768 bytes.
The FPGA runs at 25 MHz and derives the emulated 4,194,304 ticks per second from
it as an enable, so the games run at Game Boy speed rather than at whatever clock
the board happens to have.

The split is the interesting part. The
synthesizable hardware is 73 SystemVerilog files and 8,146 lines. Verification
code and program fixtures are 420 files and 43,608 lines — five times the RTL,
which is the ratio I would expect and the only ratio here I would defend as
meaningful. Host tooling is 103 implementation files and 82 test files. The work
came from 273 issues, 264 of them closed.

Nine games now have a tile in the landing-page gallery: Springtrail and
Stackdrop, which this repository builds, and seven third-party images that run on
the board. What "run" means there, and what it does not, is the subject of
[verification](#verification) below.

## Working remotely

For most of the ten days the board was in one place and I was in another, and the
only thing connecting them was a serial port. That constraint shaped more of this
project than any design decision I made deliberately.

### One channel, and everything had to fit through it

There is no JTAG session, no debugger, no screen I could see. The UART carries
everything: loading an image with a full byte-for-byte readback, running and
pausing, reading registers and memory, applying an input mask, and pulling a
frame back. <a id="host-snapshot"></a>A **host snapshot** is that last one — the
packed 160×144 framebuffer the board returns over UART for one completed frame,
identified by its sequence number and the emulated dot it completed at. It was
the only way the board could tell me what it was showing, and it is the
provenance behind almost every picture in this article.

![A board session over UART: status, a load with full readback, run and halt, an input mask, bounded execution and two frame snapshots](../showcase/uart-debugging.svg)

*The host commands of one recorded Libbet session, drawn from the retained play
record rather than sent to a board for this page. The [session
notes](../showcase/README.md#uart-debugging) list every value shown and where it
came from.*

Because the channel is narrow, execution is counted rather than timed. `run-dots`
advances an exact number of emulated dots — one frame is 70,224 — so a session
replays to the same dot every time instead of depending on how fast my phone
answered. That started as a remote-work accommodation and turned into a
verification property: a recorded session with exact dot counts is reproducible,
and a recorded session measured in wall-clock seconds is not.

### The phone

The [live viewer](../tools/n2m/host/LIVE_VIEWER.md) — the page in the screenshot
above — is a small authenticated server on the host beside the board. It reads
actual packed pixels over UART, publishes them as native PNGs, and accepts taps
from a phone browser over a tunnel. It renders no game of its own and never
loads, resets or programs the board.

It is also slow, and it had to be. Every frame is a round trip through a serial
port, so the viewer's honest description of itself is that it shows the image
already on the board, at whatever rate the link allows.

### Then a monitor arrived, and the tools changed shape

When I got back to the board and connected a VGA monitor, the most useful thing
that changed was not that I could finally see the picture. It was that the
picture no longer had to travel.

The [on-screen pad](../tools/n2m/host/GAMEPAD.md) exists because of that. It is a
desktop window with a D-pad and A, B, Select and Start, and it sends buttons and
nothing else: it reads no frames, serves no HTTP, and never loads, resets or
programs the board. All the frame-reading machinery the viewer needs is simply
absent, because the monitor is doing that job. The
[launcher](../tools/n2m/host/LAUNCHER.md) is the same idea with loading added: one
window that lists every image the board can run, loads the one you pick, resets
it, runs it, and hands over to that same pad in the same UART session.

So there are three ways to drive the board, and they are separate on purpose.
`host keyboard` needs a Windows console and shows nothing. The live viewer shows
pixels over a tunnel and sends fixed taps. The pad shows the controls and assumes
you can see the screen yourself. Each is the right tool for exactly one
situation, and the situation is where I happen to be standing.

## Directing agents

### The shape of the org chart

One agent is my single point of contact. It selects an issue and delegates it to
a <a id="crewmate"></a>**crewmate** — this repository's word for a subordinate
agent working one bounded task in its own Git worktree, defined in
[AGENTS.md](../../AGENTS.md#work). A different crewmate reviews the result before
it merges. Crewmates report to the orchestrator, never to me, and the orchestrator
reports outcomes and open decisions. I borrowed that single-contact shape from
Kun Chen's [Firstmate](https://github.com/kunchenguid/firstmate);
<a id="firstmate"></a>**firstmate** is my word for the pattern and not repository
vocabulary. It appears nowhere in `AGENTS.md`, the skills or the source; the one
place it is written down is the diagram in this article, which is a blog asset
and carries my framing rather than the repository's.

AGENTS.md caps how many pull requests one orchestration tree may have open and
how many crewmates may be active at once. The caps exist because the failure mode
of unlimited parallelism is not wasted compute, it is a review queue I cannot
read. When no slot is free, an author goes idle before its reviewer starts, and
delivery serializes. That is intended.

### Where I set direction, and where I did not

<a id="spec-driven"></a><a id="issue-driven"></a>Two words carry most of the
weight. **Issue-driven** means every change begins as one GitHub issue stating a
single observable result and three to five checkable success criteria; nothing
gets built that is not an issue first. **Spec-driven** means the behaviour itself
is owned by a written specification in the wiki, beside the code, and the
implementation and its tests are judged against that document rather than against
the author's summary.

Inside those boundaries the agents decide. Module decomposition, state machine
shape, where an assertion goes, which test proves a rule, how a host command is
spelled, whether a fix belongs in the widget layer or below it — none of that
came from me. What came from me was the issue, the specification and the scope.
The two together mean something specific and, as it turns out, dangerous: the
artefact an agent implements is a document I wrote. Everything downstream
inherits whatever is in it.

### Agents removed the bottleneck I expected and created one I didn't

I expected the constraint to be output. A module a day, maybe; the PPU would take
a week. That constraint disappeared almost immediately. A bounded change with a
written contract and a test came back in minutes, and it came back plausible:
correct package qualification, a sensible state machine, an assertion, a passing
simulation and a paragraph explaining the choice.

What replaced it was a question I had never had to ask at this rate. *How do I
know?* Not "does it compile" or "did the test pass" — those are cheap and the
agent answers them before I see the branch. How do I know that the test was
testing the right thing, that the contract it was written against was the
contract I meant, and that the passing result says something about the artefact I
am going to program onto a board.

Review is the classical answer, and it is still a good one, but reading rate is a
human constant. Production rate is not, any more. The gap between them is the new
bottleneck, and it does not close by reading faster. It closes by choosing
instruments that do not scale with my attention.

Broken output is not the danger. Broken announces itself: the elaboration fails,
the assertion fires, the frame comes back blank. The dangerous output is the one
that is coherent, well-argued, internally consistent and wrong — and agents are
extraordinarily good at producing exactly that, because coherence is what they
optimize.

### I wrote the bug three times

<a id="my-mistakes"></a>Under [spec-driven, issue-driven](#spec-driven)
development the artefact an agent implements is a document, and three of the most
expensive mistakes in this project were mine, not the agents'. Each was a sentence I wrote that read perfectly, that an
agent implemented faithfully, and that was wrong in a way no amount of care in
the implementation could have recovered. A plausible specification propagates
perfectly. That is the whole problem in one line.

**My acceptance criterion named a module that isn't in the product.** Issue #426
asked for host memory reads from a paused board. Here is the criterion, exactly as
I wrote it:

> - [ ] The OAM late-write path is shown not to straddle a pause:
>   `n2m_oam_late_write.sv` advances its phase machine on `clk_sys` with no
>   `gb_tick` gate, so either a late write in flight when `paused` asserts is
>   proven to complete before any host OAM read can be accepted, or host OAM
>   reads are additionally held off until that machine is idle, and an assertion
>   covers whichever rule is chosen.

Read it on its own and it is a good criterion. It names the file, states the
mechanism, gives two acceptable resolutions and demands an assertion either way.
It is also a precise, checkable, satisfiable criterion about a module that is never
instantiated in the product hierarchy. It appeared in a board source list, but
nothing in `src/rtl` or `src/fpga` instantiates it; its only two instantiation
sites are a testbench and a verification system. An agent could have satisfied
the letter of that criterion completely, closed the issue, and left the board
exposed.

The author of [PR #436](https://github.com/amichai-bd/nand2mario/pull/436) opened
the pull request with this:

> **Reviewer, read this first.** One success criterion names
> `src/rtl/memory/n2m_oam_late_write.sv`. That module is **never instantiated in
> the product hierarchy**, and the hazard the criterion describes is real but
> lives in a different module. Satisfying the criterion therefore required a
> small change to the DMA owner, which is outside this issue's stated scope.

The real owner of the hazard is `n2m_dma_service`, whose slot counter advances
every `clk_sys` edge ungated by `gb_tick`, so a started job can straddle a pause
for up to 22 cycles. The same pull request fixed that hazard — threading an
`oam_sequence_active` signal through to a peek-ready gate, with assertions on
both rules. The pull request says plainly that this reaches outside the issue's
stated scope. A follow-up later moved the misleading module out of the product
source lists entirely.

I want to be precise about what saved this. Not a test: a test against my
criterion would have passed. The author read the criterion, went looking for the
module in the hierarchy, and did not find it.

**My ordering made the game uncontrollable.** Issue #538 added stepped execution
to the remote viewer, and I specified the per-cycle ordering: freeze the input
batch, execute each press with its release verified, advance the step, take one
complete snapshot.

That order is correct for free-run, where dots are advancing continuously and a
bounded press lands inside them. It is wrong for stepped, and wrong in a way that
is obvious once stated. With the core halted, a press applied and then released
before the step advances is applied and released across *zero* emulated dots. The
game never observes it. `HOST_REG_INPUT` is a plain button mask with no
pending-press latch — there is nothing to hold the edge until time moves.

An agent implemented that specification faithfully and produced a game that
cannot be played. Independent review of [PR
#543](https://github.com/amichai-bd/nand2mario/pull/543) found it, with an
endpoint trace showing the press and the release both occurring while paused and
before any dots ran, and wrote the conclusion better than I would have: stepped
mode does not make a gravity game playable, it makes it uncontrollable. The fix
is press, step with the mask still held, release and verify — the order the
project's own play script had been using all along.

The detail I find most instructive is why the tests passed. The only press that
ever reached the game was one sharing a batch with a free-run-to-stepped
transition. No test issued a press while already stepped. The suite covered the
feature and missed the only case the feature exists for.

**My scope change lived in a chat message and not in the issue.** Issue #556
specified a local on-screen gamepad that would decode and display the board's
framebuffer, step by default, and report stale frames. Partway through I decided
to drop frame display, and with it stepped mode, and I told the author so in a
message.

I never wrote it into the issue. The issue's timestamps show it: last updated 23
seconds after creation, zero comments, while the tool being built had no frame
display at all. Three of its eight success criteria were unmet as written, and
`Closes #556` would have closed an issue describing a different tool than the one
that shipped.

Independent review of [PR
#558](https://github.com/amichai-bd/nand2mario/pull/558) caught it and blocked on
it. The issue was then revised, with a note recording that the revision should
have been made when the decision was taken. The review also flagged residual
stale sentences in the revised text, which is its own small lesson about how hard
it is to edit a document back into agreement with reality once it has drifted.

### And where the agents were wrong

Three specification failures of mine make a tidy story and a misleading one. The
agents produced plenty of their own, and they had a recognisable shape: not
broken code, but a claim that was narrower than it read.

**A checker that accepted states the machine cannot reach.** In [PR
#522](https://github.com/amichai-bd/nand2mario/pull/522) an agent-written
scheduling oracle for Springtrail accepted any button event inside the whole
4,560-dot VBlank as affecting that frame's update. The reviewer showed it could
not: an event at VBlank+4,559 arrives after both joypad row reads, so the oracle
was admitting combinations no run could produce. The tests were green because the
oracle was too permissive to fail. The fix derived the two read dots from the
source and looked inputs up chronologically.

**A test that proved timing rather than the thing it was written for.** [PR
#455](https://github.com/amichai-bd/nand2mario/pull/455) replaced `taskkill /T`
with a Windows job object so a timed-out Quartus run could not leave orphaned
grandchildren. The fix was right and the reviewer reproduced the defect
independently. The regression test was not: at its chosen 1.0-second spawn delay
the grandchild was never spawned at all, so five runs out of five took the
`return  # the parent died before it could spawn` branch. The reviewer measured
that the test would not have failed on the old code either. A passing test that
observes nothing is worse than no test, because it is counted.

**A limitation that was real, documented, and understated.** [PR
#471](https://github.com/amichai-bd/nand2mario/pull/471) added a check that every
Python module a test target loads is declared as an input. The specification said
it walks the import statements with `ast`. True — and the reviewer planted
`importlib.import_module("zz_planted")` in a live fixture module and watched the
check accept the target, while a plain `import zz_planted` was rejected by name.
A dynamic import already in the tree loaded fixtures for eleven targets. The
sentence was not false; it just did not say what it excluded, which for a
checking tool is most of what a reader needs.

**Confident annotation beside correct arithmetic.** In [PR
#450](https://github.com/amichai-bd/nand2mario/pull/450) every number in a
startup-timing derivation was right and independently recomputed. Two comments
around them were not: nine M-cycles attributed to the wrong routine, and a
parenthesis reading "(DI, IE 0)" where `IE` is 3 at the moment the write commits.
Nobody's result changed. But the comments are what the next reader trusts, and
they were written with exactly the same confidence as the figures that held.

The common thread is not carelessness. It is that an agent will state a
conclusion at the confidence of its strongest evidence rather than its weakest,
and will not spontaneously volunteer the boundary of what it checked. That is a
failure mode a reader can learn to probe for, which is what a reviewer is doing
when it plants a module or measures the timing of a timing test.

### Where the authority actually sits

Three of my failures, one cause: the code was right against the document and the
document was wrong. Four of theirs, one cause: the claim was stated at the
confidence of its best evidence. Both are invisible to a test, and both are
visible to a reader whose job is to disbelieve.

This is the part of agent-driven development I was least prepared for. I came in
assuming my job was to check the output. It is not, or not mainly. My job is the
input, and the input is unusually load-bearing because agents do not push back on
a premise the way a colleague does. A human engineer handed criterion 426 would
probably have muttered "wait, is that module even in the build?" — which is
exactly what the author agent eventually did, but only because the workflow gave
it standing to say so and a reviewer to say it to.

So the practical conclusion is not "write better specs", which is advice nobody
can act on. It is that specifications and claims both need adversarial reading,
and the reading is cheap. It is much cheaper than the board being wrong.

## The delivery loop

![The delivery loop: alignment, issue, isolated worktree, code and specs, tests, pull request, independent review, merge](assets/agent-flow.svg)

*The title band is the diagram's own label for the arrangement, and
[firstmate](#firstmate) is my word in it, not the repository's. Alignment is the
human-in-the-loop step: the goal, the scope and what will count
as done. After that the agents own the issue, the worktree, the code and specs,
the tests, the pull request, the independent review and the merge. Failed tests
and review findings go back to code without asking me. Only a change to the
agreed scope comes back up.*

### One issue, one branch, one worktree, one pull request

The mechanics are deliberately rigid, because rigid mechanics are what let a
dozen changes be in flight without anyone tracking them in their head.

A change starts as an assigned issue — that is what
[issue-driven](#issue-driven) means in practice. Its branch is
`<number>-<slug>` and its worktree is `worktrees/<number>-<slug>/`, one per
change, never shared. All
editing, building, validating and committing happen there, and generated output
stays in that worktree's `workdir/`. The primary checkout stays clean on `main`.
Every pull request opens as a draft and carries `Closes #<number>` on its own
line. A crewmate other than the author reviews the current head. The author
undrafts, waits for the required checks to re-trigger, and squash merges at the
exact reviewed SHA. Then the worktree, the branch and the build artifacts go
away, and a validation summary stays in the pull request.

One automated check enforces the parts a script can enforce: a valid numbered
branch, a `main` base, and closing references to open assigned issues including
the branch's own. `main` additionally requires linear history and resolved review
conversations. Human approval is not required anywhere in this, and no number of
approvals substitutes for the review having happened.

The loop is fast enough to be worth measuring. Median time from opening a pull
request to merging it was 12 minutes 28 seconds; 83.2% merged within an hour of
opening; p90 was 2 hours 12 minutes. Those intervals exclude the work done before
the pull request opened, so they are not development time. What they do measure
is queueing, and queueing is the thing that degrades when parallelism goes up.

### Review is an instrument, not a slower test

A reviewer is not a slower test. It is a different measurement entirely. A test
asks "does this behave as specified"; a reviewer can ask "is this the right
specification", "is this number actually what you measured", and "does your
evidence support the sentence you wrote". None of those questions can be
automated here, and all three found real problems in this project.

The reviewers are agents — a different [crewmate](#crewmate) from the one who
wrote the change, reading the current commit against its contract. It works
because the reviewer has no investment in the author's framing, not because it is
smarter. Independence of the reader is the same purchase as independence of the
oracle, made on the other side of the loop.

What that looks like in practice, from the first blocking finding on [PR
#558](https://github.com/amichai-bd/nand2mario/pull/558), the on-screen pad:

> **B1 — Held buttons stick when the window loses focus.** `tools/n2m/gui_pad.py:306-311`
> binds `<KeyPress>` and `<KeyRelease>` and nothing else. On Windows, the
> KeyRelease after an Alt+Tab or a click on another window is delivered to the
> new foreground window, so the held union keeps the button and the board keeps
> receiving it until the player comes back and cycles that key. The player is
> watching the VGA monitor, not this window, so the first symptom is the
> character walking away on its own.

Nothing there is a test result. It is a claim about how an operating system
delivers an event, joined to a claim about where the player is looking, ending in
the observable symptom. No suite in this repository could have produced it,
because the input it depends on never arrives in a test. The finding continues by
pointing out that `host keyboard` already treats focus loss as terminating and
documents it, so the pad was not merely wrong but inconsistent with its sibling —
which is the sort of thing only a reader holding both files at once will see.

### When the reviewer was wrong

The best example I have of review working is one where the reviewer was mistaken.

Adding a row of footer text to the games gallery came down to how much vertical
clearance was left below the tiles. The author's pull request gave a number. The
reviewer checked it, found it wrong, and filed a correction as minor, because the
margin turned out *larger* than claimed and so the decision held either way. The
author then checked the reviewer and found that both had measured the wrong
element: the binding one was the bottom row's tile credits, and the real
clearance was 18px — exactly one line of leading, and a figure neither party had
reached. The author's original number was below it and the reviewer's was above
it.

The decision still stood. But the margin it stood on was not the one either party
had measured, and at the time the number went into the generator as a comment
beside the coordinate it constrained. Neither the author nor the reviewer had it
alone; the exchange produced it. That is why "the reviewer approved it" is a
weaker statement than "the reviewer and the author disagreed about something
specific and resolved it."

### Attested versus captured

In [PR #546](https://github.com/amichai-bd/nand2mario/pull/546), one of the
success criteria was that Stackdrop could be played through the authenticated
viewer. I played it, in both viewer modes, over the tunnel, and reported that it
worked. No frames were retained.

The pull request does not say the criterion was demonstrated. It says the row
clear is evidenced by retained artifacts, and the viewer play is **attested, not
captured** — and separately, that no frames of the owner's viewer play were
retained and none are cited. That distinction survived review, because review had
blocked on the criterion being claimed more broadly than the evidence showed.

Three words. They are the difference between a record that can be checked later
and a record that is a memory of mine wearing the clothes of evidence. I am the
owner of the project; my say-so is worth something. It is not worth a frame hash,
and the record should not let a future reader confuse the two.

### What it cost

The honest answer is that I do not know, and the repository does not record it.
No token spend, no money and no hours are measured anywhere in this project, so
there is no number here to give. I would rather say that plainly than offer an
estimate, because an estimate is the one thing in this article that could not be
checked.

What is recorded is the elapsed shape. Eleven active dates from 4 September to
14 September. 303 merged pull requests with a median of 12 minutes 28 seconds
from opening to merge. A concurrency ceiling on open pull requests and active
crewmates, set in `AGENTS.md` low enough that I could still read what came back.
And two hard serializations that no amount of parallelism could buy past. The
Questa licence is one node-locked seat, and the record shows work waiting on it:
a reviewer on [PR #455](https://github.com/amichai-bd/nand2mario/pull/455) logged
six consecutive licence refusals, exit 12, because another crewmate's simulation
held the seat throughout. The board is the other, serialized by rule under
`AGENTS.md` rather than by anything I can point to as a queue — there is one
DE10-Lite, and physical access needs explicit authorization each time.

Those constraints are the real economics of this arrangement, and they are not
the ones people expect. The scarce resources were a physical board, a simulator
licence and my own reading capacity. Generating the work was not scarce.

## Hardware design

An extra output register on the vendor RAM would silently change every consumer's
latency, and a zero-latency array in simulation would have hidden it. That is why
the wrapper below simulates the same primitive the fitter places.

The product is `src/rtl/`: SystemVerilog modules that get synthesized. The Python
under `src/dv/` looks similar in places and is the opposite kind of thing — it
exists to *check* the RTL, never to be it. Every design practice below follows
from that split. You write a register macro because a register becomes a flip
flop; you wrap the vendor memory primitive because the primitive is what the
fitter will actually place; you make the timebase an enable because generating a
4.194304 MHz clock in fabric is how you lose timing closure and a day.

### The CPU

The [SM83 owner](../src/rtl/cpu/MAS_cpu.md) covers the complete legal base and
CB-prefixed instruction sets. A subset does not satisfy that contract, which is a
useful thing to write down early, because a CPU that runs your own game is a much
smaller CPU than one that runs somebody else's. The digital model follows
documented DMG-B behaviour including the HALT bug, delayed interrupt enabling and
interrupt priority changes during entry. It does not claim analogue or silicon
identity, and the [source record](../src/rtl/cpu/references.md) separates
instruction facts from measured timing, reverse-engineering evidence and
remaining uncertainty. No external CPU HDL, decode implementation or boot
contents were imported.

<a id="retirement-trace"></a>Every completed instruction or interrupt entry emits
a record — a **retirement trace** is the ordered stream of `(epoch, sequence,
kind)` records those produce, serialized over an ABI shared with anything that
wants to compare against them. This is the single most useful design decision in
the project, and its value is in [verification](#verification) rather than in
the hardware: it turns "the game looks right" into "instruction 41,332 committed
a different value than the reference did".

### Time is an enable, never a clock

The system clock is 25 MHz. The Game Boy's is 4,194,304 Hz. Nothing in this
design generates a 4.194304 MHz clock in fabric; instead `gb_tick` is an enable,
and an enabled rising edge of `clk_sys` advances exactly one emulated dot.

The arithmetic is a phase accumulator. At each active edge, add 65,536 to the
phase; if the sum reaches 390,625, assert the enable and subtract. After N active
edges the tick count is exactly `floor(N × 65536 / 390625)`. The first tick is
edge 6, subsequent gaps are five or six edges, and each 390,625-edge period emits
exactly 65,536 ticks. Every tick arrives less than one system period — under 40
ns nominal — after its ideal continuous edge, and the cumulative average error is
zero.

That last property is the point. A design that approximated the tick would drift,
and drift is the kind of defect that shows up as a game feeling slightly wrong
after ten minutes, which is the worst possible failure to debug remotely. Making
the timebase exact by construction removed a whole category of question.

The consequences run through everything else. A normal-speed M-cycle spans four
dot enables, which is 23 or 24 system edges, so every memory service must finish
within 23 edges and pipelining cannot borrow an extra emulated cycle. A missing
response is an assertion failure, not a dropped tick. And a host pause freezes
emulated state and the phase together at a dot boundary, which is what makes
`run-dots` reproducible across sessions.

Two PLLs run from the single 50 MHz board reference, in parallel and never
cascaded: the system PLL at `M=104, N=8, C=26`, and the pixel PLL at `M=63, N=5,
C=25` for 25.2 MHz. The `±100 ppm` reference bound in the
[clock contract](../src/clocks-resets-cdc.md) is an acceptance requirement the
project set itself, not a measured oscillator specification — the document is
careful about that, and so is this sentence.

### The PPU and the display path

The [PPU owner](../src/rtl/ppu/MAS_ppu.md) implements the raster you would
expect: 154 lines of 456 dots, 144 visible lines of 160 pixels, mode 2 at 80
dots, mode 3 varying with scroll, window and object fetches. Objects select the
first ten Y-overlapping OAM entries including X-hidden ones, smaller X winning
and then lower OAM index. Fine SCX is sampled at the first background map-fetch
boundary. Pan Docs is pinned at an exact commit as the shared rule source, and
Mooneye and Mealybug are pinned as behaviour research — sources for expectations,
not test ROMs imported into the build.

The VGA side is a deliberate seam. The [frame bridge](../src/rtl/vga/MAS_vga.md)
takes exactly 23,040 valid source pixels to complete a frame, in the system
domain, and hands them to the pixel domain for scanout. Gaps between pixels are
allowed anywhere; a start during a partial frame, a pixel without a start, or an
extra pixel after completion is invalid and says so. Pixel-clock stoppage does
not backpressure the source. Writing the crossing as a contract with named
illegal cases, rather than as a FIFO that mostly works, is what let the crossing
be verified separately from either side of it.

### Memory, and simulating the primitive you build

The shared [Intel RAM wrapper](../../src/rtl/common/n2m_intel_ram.sv) instantiates
`altsyncram` with MAX 10 and M9K selected, and that same instance is compiled
both for Questa against Intel's installed vendor model and for FPGA synthesis.
This matters more than it sounds. An extra output register would change the
consumer's latency, read/write collisions need an explicit contract, and reset
does not clear a physical RAM. The wrapper gates requests and validity and checks
illegal overlaps. Simulation preload feeds the vendor model an initialization
file through a simulation-only parameter path; it does not swap in a zero-latency
array. Fit and timing checks answer the separate question of whether the composed
hardware meets its physical constraints.

The [memory owner](../src/rtl/memory/MAS_memory.md) assigns exactly one storage
owner to each store — ROM, WRAM, HRAM, VRAM, OAM, wave RAM — and routes every
other consumer through an arbitrated port rather than a second array. Echo RAM
reuses the same low thirteen address bits with no second store. OAM has one
resolved write port that CPU writes, DMA and corruption updates all reach. Wave
RAM exists as storage even though nothing synthesizes audio, because the CPU is
allowed to write it and must not fault. Present-but-unimplemented is a status the
contract names, which is better than a generic shadow register file that silently
absorbs anything.

### Register intent, made visible

I cared what the code looked like, not only whether it passed. Modules use
explicit boundaries and package-qualified declarations, so the owner of a type is
visible where the type is used, without a wildcard import dragging an implicit
set of names into scope:

```systemverilog
n2m_cpu_pkg::cpu_execute_request_t execute_request;
n2m_cpu_pkg::cpu_execute_result_t execute_result;
```

Registers go through named macros carrying the clock, reset and enable contract.
One definition from [`macros.svh`](../../src/rtl/common/macros.svh), and the three
call sites it serves in the [tile decoder](../../src/rtl/display/dmg_tile_pixel.sv):

```systemverilog
`define DFF_RST_EN(Q, D, CLK, EN, RST, RESET_VAL) \
    always_ff @(posedge CLK) \
        if (RST) Q <= (RESET_VAL); else if (EN) Q <= (D);
```

```systemverilog
`DFF_RST_EN(valid_s1, valid_s0, clk, enable, reset, 1'b0)
`DFF_RST_EN(color_index_s1, valid_s0 ? color_index_s0 : 2'b00, clk, enable, reset, 2'b00)
`DFF_RST_EN(shade_s1, valid_s0 ? shade_s0 : 2'b00, clk, enable, reset, 2'b00)
```

Three lines, and each says what it is: a rising-edge register, reset taking
priority over enable, with the reset value written out. The macro holds the
nonblocking assignment once; the call sites express intent instead of repeating
process boilerplate, and separate forms cover the other reset and enable
contracts. The same file defines the assertion macros to expand to nothing under
`SYNTHESIS`, so a property is a simulation check and never accidental logic. The convention is
recorded in the [RTL style reference](../src/rtl-reference-style.md), which makes
it a recurring review expectation rather than a preference I have to restate to
each new crewmate.

That last clause is the actual reason the style reference exists. With human
colleagues, conventions propagate by osmosis. With agents there is no osmosis:
either the convention is written where the reviewer will read it, or the next
change is written in whatever style its author reached for.

## Software

### The toolchain

<a id="software-stack"></a>The repository builds its own SM83 toolchain rather
than depending on a prebuilt image. The **assembler** turns SM83 source into
objects with symbols, sections, expressions and relocations. The **linker**
resolves them and the **packager** emits a 32 KiB mapperless ROM. The **builder**
— `tools/build.py` — is the single entry point that drives software builds,
simulation, the test catalogue and FPGA compilation, recording deterministic
manifests, hashes and logs as it goes. The **host tools** own UART. The contracts
are the [build specification](../tools/n2m/SPEC.md) and the
[software-toolchain specification](../tools/sw/SPEC.md).

Writing an assembler is the kind of task agents are extremely good at and
extremely dangerous at, because an assembler that agrees only with itself will
pass every test you write for it. So it is checked against a pinned unmodified
RGBDS release as an oracle. The fixture exercises immediate and CB-prefixed
encoding, relative branching, fixed section placement, cross-object CALL
relocation and `LOW(symbol)`; RGBASM owns encoding and RGBLINK owns relocation,
and the checker compares the whole output including padding against independently
authored literal bytes. It does not read the project's own opcode tables. A
separate conformance runner covers the complete documented instruction forms.

The whole pipeline is fingerprinted. Two clean builds at different tags produce
the same fingerprint and byte-identical images; appending a comment line to a
source file misses the cache and produces a new fingerprint with the same image
hash, because the assembler ignores the comment.

![Two clean software builds at different tags, their identical image hashes, a cache hit, and a deliberate source edit that misses the cache](../showcase/reproducible-builds.svg)

*Real command output captured in one shell at commit `396b0b4`; the
[session notes](../showcase/README.md#reproducible-builds) map every line to its
source and say which JSON fields were shortened.*

### Art that matches the hardware

Game artwork follows the hardware's native representation. An 8×8 tile is two
bits per pixel stored as two bitplanes: 16 bytes. Larger characters are composed
from pieces, and maps reference shared tiles with placement and flip information,
so a pose costs a handful of tile IDs rather than a bitmap. The editable sources
are integer shade grids and placement maps; the SVG sheets are generated review
views, not authoritative art.

![Small 16x16 character poses beside the numbered 8x8 tiles each one is assembled from](../src/sw/springtrail/character-art/small-tile-maps.svg)

*A review sheet, not an FPGA capture. The composed poses show which 8×8 pieces
are reused, which is how a shared-tile mistake becomes visible before it reaches
a ROM.*

![Two asset paths from editable tiles: placement maps compose review previews, and the ROM build encodes tile atlases and links them with game software](assets/asset-build.svg)

*Previews check the art. Execution and captured pixels check its integration.
They are different questions, and the diagram keeps them apart.*

### Two games

[Springtrail](../src/sw/springtrail/SPEC.md) is a silent monochrome scrolling
platformer with walking, running, jumping, collision, pause, retry and win
states, collectibles, an enemy and a HUD. It is ordinary SM83 assembly in the
same `dmg-direct-v1` profile any other image uses: standard JOYP, standard
graphics, timer and interrupt registers, no game-specific hardware path, and a
shadow OAM image transferred through a real `FF46` DMA from HRAM. Nothing in the
RTL knows what a courier is.

![Recorded FPGA frames from a Springtrail run: title screen, a scene mid-play, and the first-stage WON screen](../showcase/springtrail-state-board.svg)

*Real frames read back from the board over UART, shown as an animation of
selected checkpoints. The [capture
provenance](../showcase/README.md#current-springtrail-state-comparison) records
what was compared.*

One detail in the specification is worth pulling out because it is the kind of
thing only hardware people write down: after each JOYP row-select write, the game
waits at least 24 DMG dots before reading the selected row. Without that wait,
transitional direction bits become actions. A game written against an emulator
that settles instantly would not need it, and would misbehave here — which is the
same class of difference that later stopped two other people's games from drawing
anything.

[Stackdrop](../src/sw/stackdrop/SPEC.md) is a falling-block game, and it exists
because a second program is a much better test of a platform than a longer first
one. Its rules are frozen in the specification down to the spawn cells of each
of the seven pieces and the rotation mapping, with no wall kicks and no random
state: the piece cycle is a fixed repeating I, O, T, L, J, S, Z. Determinism was
chosen so the game could be driven by a scripted host session and produce the
same board every time.

### The host tools, and three stuck buttons

The on-screen gamepad is a small Python window. You click or press keys, it
writes a button mask to the board over UART. It is about as simple as a tool in
this repository gets, and it shipped three separate defects that all had the same
symptom: a button the board thought was still held.

**One.** A constant `MODIFIERS = 0x4 | 0x8 | 0x20000` filtered out key events
carrying modifier bits. Tk's `0x8` was read as Alt. On Windows it is Mod1, and
Windows latches NumLock into Mod1. The filter applied only to key-downs, so with
NumLock on, every press was discarded and every release sailed through. I hit
this myself: the mouse buttons worked and the keyboard did nothing.

**Two.** Windows reports right Shift's press as `Shift_R` and its release as
`Shift_L`, both on keycode 16. Only `Shift_R` was mapped, and the keycode
fallback could not rescue the release, because keycode 16 is `VK_SHIFT` and was
not among the eight button codes. The press registered, the release vanished, and
Select stayed on at the board until the window lost focus or exited.

**Three.** In the launcher, the Back control was wired `back=show_menu` — go to
the menu, and nothing else. No release at all. With the pad panel destroyed,
neither the key-up path nor the focus-loss release that the previous fix had
added could rescue a held button.

The pad's tests are not thin. They run against a fake endpoint with no board and
no window, and they cover the button logic directly. The first two defects lived
in `edge`, a pure function the tests call. But every test passed `edge` a state
value it had chosen itself — `0`, or a deliberate Ctrl or Alt bit — and no test
used a state value a real Tk window had produced. For the Shift pair, every test
fed `edge` a keysym it had chosen, and none modelled a press and a release
arriving under *different* keysyms, because it had not occurred to anyone that
they could. The third defect lived inside a widget callback, and a window cannot
be asserted headlessly at all.

The tempting response to three bugs in one place is to be more careful. That does
not work, and it does not survive the next author. What actually changed was
where behaviour is allowed to live. The pad's widgets moved into a `PadPanel`;
the meaningful work stayed in a display-free `Driver` the tests drive directly;
and Back's behaviour became a `leave_pad` function called by a one-line binding
rather than written inside one. The rule the tool's page now states is blunt: a
window cannot be asserted headlessly, so behaviour does not live in the widget
layer.

That is not a promise that the next defect will be caught. It is a reduction in
the size of the surface that testing structurally cannot reach, to something
small enough to name and small enough to read in one sitting. That is the
realistic goal — not eliminating the untestable region, but shrinking it until
review can cover what is left.

## Verification

### How the checks are built

Questa simulates the RTL and the vendor memories. Python and cocotb organize
stimulus, independent expectations and result processing, driving the simulated
UART with the product client rather than a private testbench path, so the tests
exercise the tool people actually use.

Two different things are called "running the design" here, and the difference
matters for every claim below. A simulation compiles and elaborates the
SystemVerilog and advances it event by event in Questa, which is thorough and
slow — slow enough that the wall budgets in this section exist at all. A board
run executes the synthesized design on the MAX 10, at its real clock rates,
driving real pins. The first can inspect any internal signal and check every
retirement record. The second runs at hardware speed and can show you a picture
on a monitor. Neither substitutes for the other, and the
[verification tiers](#verification-tier) say which claims each one supports.

Budgets are explicit and small: normally at most 120 seconds per simulation and
300 seconds for an ordinary pre-merge aggregate, counting setup, build, run,
checking and cleanup. A target that measurably cannot fit declares its own
allowance in the repository with a recorded reason, up to 900 seconds. A
simulation must compile, elaborate, run *and* check an expected result; a
successful process exit is not evidence, and an unexplained warning is a failure.

The [integration verification specification](../src/dv/integration/SPEC.md) owns
the <a id="verification-tier"></a>**verification tiers**: which class of evidence
a change needs, and what each class is allowed to conclude. Ordinary changes meet
their own scoped criteria; milestone claims need declared complementary
simulation and physical matrices. It is the document that decides whether any
claim in this article is worth anything, and it is deliberately not this
article's job to summarize it.

![A test that reports PASS and a test that reports a deliberate failure, side by side in the builder's own output](../showcase/verification.svg)

*Both halves matter. A checker nobody has watched fail is a checker with an
unknown failure mode, which is why the fault-injection targets exist at all.*

### Your own tests share your misunderstandings

Suppose I misread the Game Boy's OAM DMA timing. I write that misreading into a
specification. An agent implements the RTL from that specification. Another agent
writes the reference model from the same specification, and a third writes the
directed tests.

<a id="reference-model"></a>A **reference model** is an independent software
implementation of the same contract, which a test compares the hardware against.
<a id="directed-tests"></a>**Directed tests** are hand-written stimulus aimed at
one named behaviour, with the expected result written out by hand. Both are
strong instruments and both are, here, downstream of my sentence.

![A scripted Springtrail playthrough drawn from the reference model: title, start, run, jump, pause, resume and a collision that ends in retry](../showcase/game-start.svg)

*Every pixel here comes from the independent Springtrail reference model, not
from the board: the generator drives the same `update()` the model's own tests
use, with asserts pinning tick, mode and player position along the way. A
reference model this detailed is a strong check on the hardware and no check at
all on the document both were written from.*

Every one of those checks passes. They agree because they descend from the same
sentence. The test suite is not measuring the hardware against the Game Boy; it
is measuring the hardware against my reading of a document, and it will keep
reporting green for as long as that reading stays consistent with itself. More
tests of the same kind do not help. They inherit the defect along with everything
else.

This is not a hypothetical worry about agents. It is the ordinary condition of
any verification effort where one person's understanding seeds both the design
and its checks. Agents make it sharper only because they make it cheap to produce
a great deal of self-consistent material very quickly, and because they will not
push back on a premise the way a colleague might.

Our own games do not escape it. Springtrail was written by agents against the
same interface documents as the hardware it runs on. If the documents are wrong
about JOYP, the game reads JOYP the wrong way and the hardware implements JOYP
the wrong way, and the courier walks. A playthrough that reaches the WON screen
proves that two halves of one misunderstanding fit together.

### Independence has two axes: the oracle and the stimulus

<a id="oracle-and-stimulus"></a>It took me longer than it should have to see that
"independent test" is not one property. It is two, and they are bought
separately.

The **oracle** is whatever says the answer is right. The **stimulus** is whatever
drives the design. A test can have an independent oracle and captive stimulus, or
captive oracle and independent stimulus, and those two combinations fail in
completely different ways.

The [SameBoy adapter](../src/dv/baseline/SPEC.md#independent-emulator-and-retirement-traces)
in `src/dv/sameboy/` buys the oracle, and buys it deeply. It runs the pinned
third-party SameBoy core `213a12ce` alongside the design and compares ordered
[retirement traces](#retirement-trace). Note which way round that is: SameBoy is
a software emulator and it is the *reference*; our SystemVerilog is the thing
under test. The adapter checks every architectural
value, every fetched byte and every completed-dot count exactly, plus every
visible pixel before VGA conversion, and fails at the first difference. That is
far stronger than "the game booted". If my reading of the CPU is wrong, SameBoy's
reading disagrees at the first instruction where it matters.

But SameBoy runs *our programs*. The stimulus is still ours. It exercises the
paths Springtrail happens to take, in the order Springtrail happens to take them.
An unusual sequence nobody here thought to write is invisible to it, no matter
how good the oracle is.

The [Mooneye targets](../../src/dv/mooneye/README.md) buy some of both, and buy
very little of either. They run one case — `acceptance/bits/reg_f.s` from a
third-party hardware acceptance suite — with `mooneye-corrupt` and
`mooneye-missing` as fault-injection variants of that same case, there to prove
the checker can fail rather than to widen coverage. One case is one case.

### What it costs to buy the other axis

Foreign stimulus is what the repository was missing, and homebrew games are how
you buy it. Eight freely licensed Game Boy games by eight authors who have never
seen this project, each pinned by SHA-256 and fetched at run time, none of their
bytes committed. They drive the CPU, PPU, timers, interrupts, joypad and memory
in combinations nobody here chose, for reasons nobody here knows. And they do it
on the synthesized design on the board rather than in simulation, which makes
them a different kind of evidence again: whatever the fitter actually built is
what executed them.

The oracle you get in exchange is crude. There is no [reference
model](#reference-model) for somebody else's game, so no pixel is compared
against an expectation. All you learn is what the board displayed, not that it
displayed the right thing. That is a real and severe limit, and it is the price
of the axis.

![The games running on the DE10-Lite, each tile a looping set of framebuffers the board returned over UART](../showcase/games-gallery.svg)

*Every game the board has been captured running, each frame read back from it.
The panel is not decoration: it says what the picture leaves out, which is the
only reason the picture can be published on its own.*

The right way to describe this is "widen", not "deepen" and certainly not
"first". The repository already held the design at arm's length twice, narrowly.
Eight full games make the narrow thing wide. They do not make it deep, and they
localize no fault: a game that plays tells you nothing about *where* a defect
would be if there were one.

### Six played, two never drew a frame

Of the eight homebrew images, six boot and play: Airaki, GB Wordyl, Max Pirate,
Alien Invasion, Square Fall and Unstoppable Knight. Counting Libbet and the Magic
Floor, which the project had run earlier, seven of the nine pinned third-party
images play. Each capture is a [host snapshot](#host-snapshot) taken in a
recorded session, with the loaded image's SHA-256 verified and all 32,768 bytes
read back before the run.

![Airaki running on the DE10-Lite: the intro, the title screen, and the match board with health bars and round timer](../showcase/homebrew-airaki.svg)

*furrtek's Airaki, pinned by digest, playing on this hardware. Nobody here chose
which registers it touches or in what order.*

The six that played were satisfying. The two that didn't are the reason the
exercise was worth doing.

Wyrmhole and Rex Run both load, both execute, and neither ever produces a frame.
`SNAPSHOT` answers `NO_FRAME`. The board reported `LCDC`, `STAT`, `LY` and `BGP`
all `0x00` throughout, while the [retirement](#retirement-trace) counters climbed
steadily — a CPU that is very busy doing nothing.

Each ROM says why, and both say the same thing. Both wait for the LCD *before*
they enable it:

- **Wyrmhole**, at `0x6370`, immediately before the `LCDC` write at `0x6377`
  that is first on its init path: `LDH A,[rLY]` / `CP 144` / `JR C,-6`, then
  `XOR A` / `LDH [rLCDC],A`. It polls `LY` until VBlank so it can switch the LCD
  off safely. With the LCD already off, `LY` is parked at 0. This is the only
  `LY` read in the image; it writes `LCDC` in four other places, all past this
  point.
- **Rex Run**, at `0x117A`: `LDH A,[rSTAT]` / `AND 3` / `CP 1` / `JR NZ,-8`,
  then `LDH A,[rLCDC]` / `AND 0x7F` / `LDH [rLCDC],A` at `0x1186`. It waits for
  `STAT` to report mode 1, which the mode field never reports while the LCD is
  off. The three instructions at `0x1174`–`0x1179` are `LDH A,[rIE]` / `AND 0` /
  `LDH [rIE],A`, so interrupts are masked and nothing can break it out.

### This wasn't a bug, it was a contract difference

A real DMG's boot ROM hands control to the cartridge with `LCDC` = `0x91`, the
LCD already running, so both loops exit on their first iteration there. This
platform has no boot ROM. Its <a id="entry-state"></a>**entry state** —
`dmg-direct-v1`, the register and memory condition a program finds when it starts
here,
[defined](../src/rtl/interfaces/MAS_interfaces.md#direct-entry-and-reset) in the
interface contract — begins with the LCD and audio off, and the contract says in
so many words that this is *not* a claim about DMG power-on or Nintendo post-boot
state.

That entry state is a hardware contract, not a setting somebody forgot to tick.
There is no boot ROM in the design and no register file quietly initialized to a
post-boot image; the LCD is off after reset because reset clears it, and the
generated profile the CPU applies at core reset is the one the interface document
defines. Changing it means changing what the hardware does at reset.

So both games are correct for the machine they target, and this machine is
correct for the contract it declares. It is not a PPU defect, not a CPU defect
and not a timing defect. It is a documented difference between two entry states,
and these two games are the first third-party code to depend on it. The other six
enable the LCD themselves before waiting on it, which is why they are unaffected.

Closing the gap would mean entering third-party images with the post-boot
register state instead of the project's own. That is a change to the entry
contract, not a bug fix, and nothing here proposes it.

### Only foreign stimulus could have found it

This is the part I keep coming back to. No test in this repository could have
produced that finding, and not because the tests are weak.

Our own games start by enabling the LCD, because they were written against [the
same entry contract](#entry-state) the hardware implements. The [SameBoy
adapter](#oracle-and-stimulus) applies the same documented `dmg-direct-v1`
initial state on both sides by design — that is what makes the comparison valid —
so the difference cancels exactly. The Mooneye case does not touch the LCD. A
[directed test](#directed-tests) would have had to be written by someone who
already suspected the answer.

The finding required a program written by a stranger, for a slightly different
machine, that happened to care. That is not a gap in our test plan that better
planning would have closed. It is structurally outside what stimulus we author
can reach, which is the entire argument for buying the other axis.

### How I knew it was really the loop

"Retirements climb steadily, consistent with a tight polling loop" would have
been a reasonable place to stop, and it would have been much weaker than what the
numbers actually support.

Each sampling interval is 60 frames: 4,213,440 dots. Wyrmhole's loop is three
instructions costing 12 + 8 + 12 = 32 dots. Rex Run's is four costing 12 + 8 + 8
+ 12 = 40. Both divide the interval with **remainder zero**: 4,213,440 ÷ 32 =
131,670 whole iterations, and ÷ 40 = 105,336. Multiply by instructions per
iteration and the predictions are 395,010 and 421,344 retirements. The board
reported exactly those figures, on every interval — three intervals for Wyrmhole,
two for Rex Run, with no variation.

A zero remainder leaves no room for a partial iteration, and no room for any
other instruction anywhere in those 4.2 million dots. That is stronger than a
consistent rate: across the whole observation each CPU executed that loop and
nothing else. The two figures are also mutually exclusive. Wyrmhole running Rex
Run's loop would have retired 421,344 per interval; Rex Run running Wyrmhole's
would have retired 395,010. Each read its own.

I like this because the confidence came from arithmetic that could have failed.
Had the remainder been 17, or had one interval read 395,013, the explanation
would have been wrong and I would have known immediately. A claim that cannot
come out wrong is not evidence, and most of the work of verification is arranging
for claims that can.

### Saying what the evidence does not show

The homebrew page could have said that other people's games run correctly on this
hardware. Its second paragraph says the opposite: this is boot-and-play evidence,
not a correctness proof; no [reference model](#reference-model) exists for any of
these games, so no pixel there was compared against an expectation; the record
says what the board displayed, not that it displayed the right thing.

Every one of those sentences reduces the apparent achievement and none of them
reduces the actual one. What they buy is that the remaining claims can be relied
on. A page that has already told you what it cannot prove is a page you can read
quickly, because you no longer have to discount it.

### Understating your own rigour is the same error as overstating it

An earlier draft of the paragraph explaining why other people's games are
evidence said the homebrew games gave independence "our own tests structurally
cannot have". It read well and it was false. The [SameBoy
adapter](#oracle-and-stimulus) and the Mooneye targets already provide exactly
that kind of independence — narrowly, but they provide it — and the repository's
own specification says so.

Review blocked on it. The corrected sentence is that the repository already holds
the design at arm's length twice, narrowly, and eight full games *widen* it. The
gallery's own footer changed a single word, from "our own tests cannot give" to
"our own games cannot give", which is the true statement.

I want to name this failure mode precisely, because I think it is
under-discussed. Modesty is not automatically safe. "We had no independent check"
is a claim about the world, and it was wrong, and a reader who believed it would
have concluded that a CPU trace comparison against a pinned third-party emulator
did not exist. An overstatement invites unwarranted trust; an understatement
hides a real control and makes the eventual accurate description look like a
retreat. Both are errors in the same direction: the record no longer says what is
true.

## DevOps

A rule that can only be obeyed by lying gets lied to. The catalogue and the
hosted-versus-local split below make the expensive path explicit, or people will
report a cheaper path that did not happen.

### One builder, one tag, one immutable receipt

Everything executable goes through `python tools/build.py`. Software builds,
simulation, the test catalogue, FPGA compilation and host contract checks are all
subcommands of the same dispatcher, and each run is named by a `--tag` that owns
a directory under `workdir/builds/<tag>/`. Within a tag, every invocation writes
an immutable `runs/<id>/` holding the exact commands, raw exit results, logs,
artifacts and a hashed result. Immutable artifact hashes name the snapshot, so a
later cache or pin failure cannot retroactively invalidate earlier evidence.

Caching is fingerprint-based and conservative. A repeated identical simulation
reports `CACHED`; a changed backend, tool identity, source, target, seed or
runner invalidates the fingerprint. Cache hits still probe explicit tool
versions. A deliberately failing target is cached too, because an expected
failure is a result like any other. Readiness is never cached: `doctor` compiles,
elaborates and runs a checked smoke every time it is asked.

![A build and test session as it prints: software build, unit tests, builder checks and one Questa simulation](../showcase/build-and-tests.svg)

*Recorded command output, not a live terminal; the [session
notes](../showcase/README.md#build-and-tests) say which fields were shortened.*

The host tools follow the same discipline. Every command prints one sorted JSON
object, every session runs under a tag, and the packet journal and result file
land beneath it. That is why a session recorded a week earlier can be quoted
exactly in a document later, without anyone having to remember what was typed.

![A board session over UART: load with full readback, status, an input mask, bounded execution, a frame snapshot and its CRC](../showcase/board-session.svg)

*Recorded command shapes, not a live capture.*

### The test catalogue

[`src/dv/builder/catalogue.yaml`](../../src/dv/builder/catalogue.yaml) holds one
entry per **runnable unit**: every registered simulation target and every
standalone `test_*.py` file in the tree. A runnable unit is the smallest thing
that can be executed alone, which is what makes a recorded duration meaningful.

Each unit declares a `level` — 0 buys quick confidence that nothing broke, 1 is
more thorough, 2 is everything, and selecting a level runs every level below it —
plus a set of labels from a vocabulary the file itself declares, and the wall
time of its last actual run. Regression subsets are declared in the repository
rather than assembled on a command line, and a subset has no member list of its
own: its members are the catalogue targets carrying its label. That is the part I
would copy into any project. There is one list of tests, and selection is a view
over it, so a test cannot quietly fall out of a suite by being removed from a
second file nobody updates. `build.py check` fails naming the first test file the
catalogue does not cover.

FPGA compilation sits outside all of that and is measured separately, by the
rules in [AGENTS.md](../../AGENTS.md#verification-and-safety). It is the one step
with no software analogue: Quartus maps, fits, assembles and times the design
against the exact device, and the build is accepted only on its reports —
map, fit, assembler and timing, a nonempty SOF, the exact-device fit summary, no
unconstrained or ignored clock and I/O paths, no structural timing problems. A
zero exit code from the tool is not a result. Programming the board over JTAG is
separate again, needs explicit authorization, and serializes: there is one board,
and two crewmates cannot have it.

An `ordinary` subset cannot declare more than 300 seconds. Anything larger is a
broader aggregate that `regress` refuses unless the caller passes `--broader`,
and it records that the flag was used. Making the expensive path explicit rather
than forbidden is what keeps the budget honest.

### Hosted versus local

Hosted runner minutes are billed, so almost nothing runs hosted. Exactly two
workflows run automatically: `PR policy` on every pull request, which reads
metadata for a few seconds and builds nothing, and `Pages` on every push to
`main`, which runs the issue-helper tests, the workspace-lock tests and the wiki
check before publishing. The rest of `.github/workflows/` never fires by itself:
three run only on explicit dispatch, for a second opinion on a clean runner when
an author or reviewer asks for one, and a fourth is guarded `if: ${{ false }}`
and has never run at all.

Everything else runs locally before merge, in the author's own worktree, on the
reviewed head, with commands and results recorded in the pull request; the
required set is scoped by what changed, down to the simulation evidence the
[verification tier](#verification-tier) selects. A local failure blocks the merge
exactly as a red hosted check would.

I would not recommend this unconditionally. It works here only because the
evidence requirements are written down, every run leaves an immutable receipt
under a tag, and a reviewer reads the recorded commands against the claimed
criteria. Remove any one of those three and "we ran it locally" is worthless.

### The wiki is the product, too

The documentation site is generated from the repository by `tools/wiki/`, and its
check is not a link-lint. Markdown links resolve against the original source
path, and a missing tracked target *or a missing anchor* fails the build, so a
heading renamed in one document breaks every cross-reference to it immediately
rather than a month later. Published files are scanned for binary content, and
the scan rejects binary extensions, known binary signatures, invalid UTF-8 and
control bytes. There is exactly one owner-authorized binary exception in the
whole repository — the phone screenshot at the top of this article — pinned by
path and SHA-256. Everything else you have seen here is SVG or text.

A second stage drives a pinned headless Chromium over the built site and checks
real interactions: category filtering, source overlays, slide deep links,
keyboard paging, print emulation, and that figures fit their column and charts
scroll rather than shrink at narrow widths. Console errors and page exceptions
fail the run. Merges to `main` publish automatically; the repository is private
and the site is public, which is a deliberate asymmetry and the reason the
binary-and-secrets scan covers unpublished files as well.

### A picture travels without its caption

The games gallery is an animated SVG. It is exactly the kind of thing that ends
up in a post, a chat, a slide, with the caption stripped off. So it has to be
true standing alone, and everything it implies has to be true too.

Its title strip therefore names no total. It says which machine the games run on
and where the frames came from, and stops there. A tile count is not a count of
what runs, and the artwork cannot know, once it has travelled, how much has been
captured since it was drawn: any number in that strip is a claim that goes stale
without anyone touching it.

What it leaves out is named inside it, in a panel headed "Not the complete set"
that identifies Wyrmhole and Rex Run as pinned images which load and execute but
never enable the LCD, so the board completes no frame to capture, and states that
seven of the nine pinned images play.

Building the disclaimer into the artwork rather than the caption costs layout — a
cell while the grid had a spare one, a band beneath the tiles once they filled
it. The alternative was a picture that told a small lie whenever it travelled,
which is most of the time.

### One exemption, defined tightly enough to be safe

[Repository statistics](../project-statistics.md) is a committed snapshot, not a
live dashboard; a scheduled script regenerates it without an agent and merges it
without a review. That is the only exemption from independent review in the
repository, and it survives because it is mechanically bounded: branch name,
title, body, base and changed-file set must all match an exact form, with the
file list read from the API rather than the description, and any other pull
request touching that file fails. Exactly one kind of change here needs no
judgement, and the way to allow it safely was to define it so tightly that
nothing else can wear its clothes.

## What this does not do

[The system](#the-project) has edges, and they are scattered through this article
as they come up — the right place for each and the wrong place to see the whole.
Collected:

**It is silent.** The [charter](../src/project-charter.md) excludes audio.
`FF10`-`FF3F` is served so a program's writes do not fault, and nothing is
powered and nothing is synthesized. Full APU completion and physical audio are
deferred, and these releases prove silent video and input, not full DMG
compatibility.

**It loads one cartridge shape.** 32 KiB, `dmg-direct-v1`, cartridge type `0x00`,
no mapper and no cartridge RAM. An image with any MBC cannot load at all — not
"runs badly", cannot load — though what actually refuses it is the size check,
which rejects anything that is not the direct-profile image size before the
serial port opens. Additional mappers, CGB, SGB and link support are all
deferred.

**It does not claim to be a Game Boy.** The charter targets the DMG family
without claiming exact silicon identity or universal compatibility, and requires
undocumented or revision-dependent behaviour to be resolved explicitly before the
affected RTL rather than assumed.

**Two pinned games never draw a frame.** Wyrmhole and Rex Run, for the entry-state
reason above. That is a real limit of this machine even though it is not a defect
in it.

**Two Stackdrop simulation targets have no headroom.** `python-stackdrop-unit`
and `python-stackdrop-game` measure 278 s and 274 s against a 288 s execution
limit, and the game target has already failed once with `test wall budget
exhausted` while a build and a wiki check ran alongside it.
[Issue #555](https://github.com/amichai-bd/nand2mario/issues/555) is open for it.
A level-0 result that depends on what else is running is not the kind of green I
want to argue from.

**One observation is not in the wiki yet.** I pressed KEY0 and reported what
happened;
[issue #512](https://github.com/amichai-bd/nand2mario/issues/512) is open and the
bring-up page still records the asserted direction as unverified.

Written out together this reads as a description of a working machine with known
edges. Left scattered, the same facts read as caveats leaking out of a claim that
was too big. The facts did not change.

## What only a person could do

Almost everything in this project was done by agents, and I have tried to be
honest about how little of it needed me. But three moments did, and what they
have in common is specific.

### Pressing KEY0

The DE10-Lite's `board_reset_n` comes from the onboard KEY0 button. Bring-up
established that the released level is not inverted — the design came out of
reset and answered over UART, which proves that much. But the asserted direction
had never been exercised. Nobody had pressed the button. The [bring-up
page](../src/board-bring-up.md) said so in as many words: unverified, needs
physical presence.

So I pressed it, and reported what I saw, which was that the monitor went dark
and did not recover. My first reading was that I had broken something.

I had not. That is the specified behaviour. `board_reset_n` drives the clocking
block's global reset, which reaches the whole system; global reset clears
transport state, frame ownership, mailbox phases, valid flags and counters, and
the display path drives RGB zero with sync inactive until a complete frame
exists. With the emulated state cleared and no image loaded, there is no frame,
so the screen stays black. The dark screen *was* the answer. The asserted
direction works.

I am recording this while [issue
#512](https://github.com/amichai-bd/nand2mario/issues/512) is still open and the
bring-up page still says nobody has pressed it, because the observation has not
been written back into the wiki yet. That is a real gap in the record, and it is
the correct place to mention it rather than round it off.

### Looking at a monitor

Every VGA test in the repository passes. Raster geometry, buffer ownership, bank
reuse, active-swap failures, source-to-VGA RGB replicas with canonical CRCs,
block-RAM inference, constrained timing. A frame could be scanned and read back
over UART and compared pixel for pixel. None of it answers whether a physical
monitor, fed by this board's actual analogue output, displays a picture.

[Issue #417](https://github.com/amichai-bd/nand2mario/issues/417) asked exactly
that question, and no agent could answer it. It closed when I connected a monitor
and looked. That single observation also closed GAP-006 — the clock, reset and
CDC gap in the preflight register, open since the register was created on
4 September, roughly nine days in all, and the last P0 blocker in it to close.

The record is careful about what this bought: one direct visual observation, for
one bitstream, one image and one monitor. Not a timing measurement, not a signal
quality measurement, and not tolerance across displays, which stays open in a
separate gap. That is a small claim. It was also the only claim that a simulator
was structurally unable to make.

### Capturing keystrokes from my own window

When the gamepad ignored my keyboard, no agent could reproduce it. The tests run
against a fake endpoint with no board and no window, and the behaviour depended
on what a real Windows Tk window puts in a real event.

So I captured the events from my own window and pasted them in. `state=0x00008`
on the key-downs. The same bit on `Shift_R`'s press, and `state=0x00009` with
keysym `Shift_L` on its release, both on keycode 16.

Those few lines found not one defect but two. The `0x8` explained the dead
keyboard. The `Shift_R` / `Shift_L` pair was something nobody was looking for,
and it was the worse of the two: a dead keyboard is obvious and a Select button
silently stuck on at the board is not. The resulting issue is titled for both,
because both were in the same capture.

### What that says about the division of labour

The three moments have one structure. Each required an observation that no amount
of reasoning, simulation or code could produce, because the fact being observed
lived outside the system's model of itself: a physical button, an analogue
display, an operating system's event stream.

That is a small and well-defined class, and it does not grow with the size of the
project. It is not "the human checks the agent's work" — I was a poor checker and
the record shows it. It is "the human is the only available instrument for a few
specific measurements". Knowing which measurements those are, in advance, is
worth more than a general commitment to supervision, because a general commitment
gets spent on the ninety-nine occasions where it adds nothing and is exhausted by
the hundredth.

## What I'd carry into the next one

### Buy the axis of independence you're missing

Go through the tests you have and ask, of each one, which half is the independent
half: [the oracle or the stimulus](#oracle-and-stimulus). Most suites turn out to
be deep on one axis and close to empty on the other, and the instinct when
confidence is low is to buy more of the axis you already own. If your stimulus is
captive, a better oracle will never find what a stranger's program finds by
accident.

### Make the conventions readable by whoever shows up next

With human colleagues, style and judgement propagate by osmosis. With agents
there is none. Every convention that matters — the register macros, the test
catalogue as the single list, the branch and worktree shape, what a pull request
must record — had to be written where the next crewmate would read it, or it did
not survive contact with the next change. The repository's rules files are not
bureaucracy here; they are the only transmission mechanism there is.

### Write the failure into the record, not around it

The two games that never draw a frame are the most valuable result on the
homebrew page, and they are the one section with no picture in it. The reviewer
who measured the gallery's clearance was wrong, and writing that down rather than
quietly correcting it is why the right number reached the generator at all. My
[three specification mistakes](#my-mistakes) are in this article because a
record containing only successes is not a record without failures; it is a
record whose failures are unaccounted for.

This is not a moral point. It is that the alternative costs more. An incident
written down honestly is a control for next time. An incident rounded off is a
thing you will do again, plus a record you now have to discount.

### Three human moments beat three hundred supervised ones

The most surprising number in this project is three. Three occasions where a
person was genuinely required — across the ten days I was away, and across the
303 merged changes the snapshot counts over its slightly longer window. I spent
far more attention than that, and most of it bought nothing, because I was
reviewing code — which [reviewers](#crewmate) do better than I do at that volume
— instead of doing the two things only I could do: getting the specification
right, and standing in front of the hardware.

I would not describe any of this as trusting the agents. Trust is not the
mechanism and it is not the goal. What I have instead is a set of instruments
that can each come out wrong: a foreign program that can hang, a reader whose job
is to disagree, arithmetic with a remainder that could have been nonzero, and
occasionally my own eyes on a monitor. Confidence is what those produce when they
are pointed at different things and none of them fails. That is what verification
has always been. What changed is only that producing the work is no longer the
expensive half.

---

*Written with AI assistance from my own account of the project and from dated
repository evidence. Technical claims link to the source, test, issue or pull
request that produced them. This article is editorial history dated 14 September
2026; the linked specifications, not this page, define current behaviour.*
