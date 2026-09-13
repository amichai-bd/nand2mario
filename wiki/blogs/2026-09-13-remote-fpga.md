# Building a Game Boy on an FPGA with AI agents—from my phone

*Project retrospective · Evidence through 13 September 2026*

I'm Amichai, a chip design engineer at NVIDIA, previously at Intel. This is a
personal project: building the hardware was familiar territory; directing its
development and testing entirely from a phone was the experiment.

I was away on reserve duty, without physical access to my PC or FPGA. Before
leaving, I had installed the ChatGPT app and connected the board and its UART
adapter. That small piece of preparation turned into a surprisingly large
experiment: could I direct agents from my phone, have them build and verify a
Game Boy-style computer at home, and eventually play its game from the same phone?

<a href="../tools/n2m/host/LIVE_VIEWER.md"><img src="../tools/n2m/host/assets/live-viewer-phone.jpg" width="300" alt="Phone screenshot showing FPGA pixels, game controls and command history"></a>

*My phone viewing actual FPGA pixels read through UART, with queued button
controls and execution history below. This is a browser screenshot, not a camera
view of the physical monitor.*

## TL;DR

I am a chip design engineer at NVIDIA, previously at Intel. While away on reserve
duty, I directed AI agents from my Android phone to build a Game Boy-compatible
system on a DE10-Lite FPGA at home. Before leaving, I had set up the ChatGPT app
and connected the FPGA and UART adapter. After that, the work was remote.

I supplied prompts, engineering direction and feedback. The agents wrote the
original project code and handled issues, branches, verification, reviews and
merges. That includes hardware RTL, design verification, an assembler and linker,
original games, host tools and the website documenting the work. The project also
uses existing tools and third-party software; agent authorship does not mean we
invented Questa, Quartus or every dependency.

The result is a system that executes SM83 game software on FPGA hardware, renders
Game Boy graphics and exposes VGA and UART interfaces. We built Springtrail, an
original platformer, and Stackdrop, a falling-block game. A bounded run of the
external game Libbet provided another compatibility exercise. UART can load a
supported game without reprogramming a compatible FPGA bitstream, read memory
and registers, capture rendered pixels and apply button inputs.

The AI workflow was as deliberate as the hardware. A Firstmate orchestrator
coordinated specialist crewmates across RTL, DV, software and FPGA work. Specs
lived beside code. AGENTS.md and focused skills turned engineering corrections
into instructions future sessions could use. Separate worktrees, independent
AI reviews, finite acceptance criteria and limits on active work kept delivery
manageable. The single Questa seat and the board required serialized access.

Some of the most consequential decisions came from steering that workflow:
insisting on readable package-qualified RTL and register macros, using Intel's
actual M9K simulation model, moving to a 25 MHz implementation clock while
preserving Game Boy time, and adopting continuous Python verification. We also
had to correct tests, deployment mismatches and process-lifetime bugs. End-to-end
AI delivery still needed clear engineering judgment and evidence at each boundary.

The most satisfying demonstration was closing the loop back to the phone. The
host reads actual FPGA pixels over UART and serves them through an authenticated
web page. I can queue button taps and see when they execute. The feed normally
updates about every two seconds; it is a remote gameplay proof of concept, not
video-rate streaming. It made the outcome tangible: I could interact with the
machine the agents had been building, without returning to the desk.

![Recorded FPGA frames: title, dynamic scene and first-stage WON](../showcase/springtrail-state-board.svg)

*Actual UART-read FPGA frames from a recorded session, displayed as an animation
of selected checkpoints. This is not a continuous live video. The
[capture provenance](../showcase/README.md#current-springtrail-state-comparison)
describes the independent full-frame comparisons.*

## The phone was the control room

The practical access chain mattered as much as the model. I used Termius and
Tailscale for SSH access to the home machine, going through Windows WSL into
PowerShell when necessary. I also used the Android ChatGPT remote experience
and, later, the Android Claude app connected to Claude Code remote sessions. The tools changed, but
the working directory, issue history and build records gave the work somewhere
to persist outside a chat window.

I started with the $200 ChatGPT plan, mainly using the model labeled Astra for
the first three or four days. I used weekly-limit resets roughly daily, then
exhausted them. To keep going, I also bought the $200 Claude plan, installed
Claude Code remotely through the WSL-to-PowerShell access path, and mainly used
Fable 5.1. That is my account of the labels and subscriptions I used. The exact
usage totals and switch dates still need filling in; the repository records
merges, not which token budget funded them.

> **FIXME (owner input):** Add the dates, or approximate days, when ChatGPT
> credits ran out, resets were used, and Claude was installed. The merge dates
> below are known; they do not establish the dates of these personal events.

> **FIXME (owner input):** Add token or usage totals by provider/model if available,
> with the covered period and what each number measures. Two subscription prices
> alone do not establish total spend or token consumption. Leave unavailable
> figures explicitly unknown; private account exports need not be published.

## Organizing the agents: the engineering control loop

The Firstmate orchestrator served as the engineering lead for the agent team. Its job was to
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

The workflow itself became a maintained part of the project. AGENTS.md held the
mandatory rules; focused skills explained repeatable methods for RTL, DV, FPGA
work, issue authoring and review. Issue templates made the desired result and
acceptance criteria explicit. Those files gave a new session a way to recover the
working agreement when the previous conversation or its token budget ended.

Concurrency needed limits. We capped active crewmates and open PRs so that
review and merging could catch up with authors. The configured caps changed
through the project; they were not a target to keep every worker busy. Questa
also had one licensed simulation seat. More authors could prepare tests in
separate worktrees, but they could not all run licensed simulations at once.
That made resource ownership part of scheduling, alongside code ownership.

### Borrow the ideas, adapt the engineering

I developed much of the workflow by telling the agents how I wanted the project
to run. Along the way, I found established skills with similar ideas and used
them as references. The issue-based task breakdown and delegation resemble
patterns in Matt Pocock's skills, although I would not claim that every part of
our flow was derived from them. These references deserve credit:

| Reference | Author / source | What I took into this project |
|---|---|---|
| Firstmate | Kun Chen — [@kunchenguid](https://x.com/kunchenguid), [Firstmate repository](https://github.com/kunchenguid/firstmate) | One orchestrator as my point of contact, coordinating crewmates and isolated work. |
| `/grill-me` and related workflow ideas | Matt Pocock — [@mattpocockuk](https://x.com/mattpocockuk), [skills repository](https://github.com/mattpocock/skills) | Challenge ambiguity before implementation; a reference for related task-breakdown and delegation ideas. |
| Superpowers and brainstorming | Jesse Vincent — [author](https://fsck.com/), [Superpowers repository](https://github.com/obra/superpowers) | Deliberate design alignment, composable skills and a structured development process. |

I did not study every upstream skill in depth or adopt a framework unchanged.
Even creating our own skills was largely prompt-driven. I gave the agents my
take on the ideas and the behavior I wanted, then had them adapt the instructions
for chip design. A hardware change has clock,
reset, memory-latency and synthesis consequences. A simulation can pass while
the programmed FPGA still contains an older design. One licensed simulator and
one physical board also make unconstrained parallel execution impractical.

Our adaptations made those concerns explicit: package-qualified RTL and register
macros; vendor memory models; independent checks of retirements, transactions
and pixels; source and tool identities attached to results; early fit/timing
checks; and serialized hardware access with recoverable process lifetimes.
Those are the project's choices, not claims about what the upstream authors
prescribed. The [local grill-me skill](../../.agents/skills/grill-me/SKILL.md)
records its pinned upstream revision and license; the broader influences above
credit the ideas without implying that we installed every upstream feature.

### The instructions evolved through feedback too

I did not carefully read and approve every line of the skills or AGENTS.md.
When an agent behaved differently from what I wanted, I described the problem
and asked it to update the persistent instructions. That might mean finishing
open PRs before starting more work, keeping the root as my single point of
contact, changing concurrency limits, or following a particular RTL convention.
The agents wrote those changes as well as the product code.

The history shows the rules evolving during the project: making the root the
[single point of contact](https://github.com/amichai-bd/nand2mario/commit/a200c89c),
giving authors ownership of
[delivery mechanics](https://github.com/amichai-bd/nand2mario/commit/4b6b1e18), and
[shortening feedback loops](https://github.com/amichai-bd/nand2mario/commit/31e002e0).
Those commits establish that the instructions changed; my description of how
I prompted those changes is my firsthand account.

This was an evolving control loop: observe agent behavior, clarify the intent,
update the instructions, and see how the next work proceeds. It also has a
limitation: an instruction written by an agent can misunderstand the correction
or interact badly with another rule. Having a skill file was never enough on
its own to establish that the behavior was right.

### Techniques that made the agents useful together

| Technique | How it worked here | Why it mattered |
|---|---|---|
| Spec-driven implementation | Contracts and acceptance criteria accompanied the source. | A reviewer could compare behavior with a written requirement. |
| Specialist ownership | Authors handled bounded RTL, DV, software or tooling tasks in isolated worktrees. | Different disciplines could progress without sharing an unstable checkout. |
| Persistent skills | Corrections to RTL style, FPGA operation and verification became reusable instructions. | A session restart did not have to erase what we had learned. |
| Independent AI review | A different agent reviewed the current commit; fixes required confirmation. | An author's summary was not the sole basis for merging. |
| Work-in-progress limits | Caps constrained active crewmates and open PRs; ready work took priority. | More generated code did not automatically mean more completed work. |
| Evidence-driven verification | Tests used independent expectations, fault witnesses and source/tool identities. | Passing results had to mean something about the candidate being delivered. |
| Repository handoffs | Issues, specifications and concise handoffs carried state across sessions and models. | Switching tools or exhausting a budget did not require restarting the project. |

![State machine for AI implementation, verification and delivery](assets/agent-flow.svg)

*The human-in-the-loop step is alignment: `/brainstorming`, `/grill-me` and
relevant skills help define the goal, scope and acceptance. Agents then own the
issue, isolated branch/worktree, code and specs, tests, commit/push/PR, independent
AI review and CI, merge and delivery checks. Failed tests and review/CI findings
return to code and specs without routine human approval. A decision that changes
the agreed scope or requires new authority returns to alignment.*

A useful example was RTL style. A generated sequential block could behave
correctly while still being unlike the code I wanted to maintain. I asked for
explicit package ownership and the register-macro convention. Recording that in
the RTL skill made it a recurring review expectation. The same pattern applied
to real vendor memory models and to FPGA operating procedures: feedback became
part of the working system, not just a correction in one conversation.

### The directory tree was part of the interface

A small map helped an agent find both a component and the evidence expected of it:

```text
src/
  rtl/       Synthesizable hardware and shared interfaces
  dv/        Hardware verification, models and checkers
  sw/        Original games and their editable assets
  fpga/      Board integration
tools/      Host clients, builds, software tools and wiki publishing
wiki/       Owning contracts, architecture, presentations and articles
.agents/    Reusable agent skills
worktrees/  Isolated issue checkouts; generated output in each workdir/
```

The source owners and their contracts are linked through the
[ownership map](../ownership.md). A CPU change has software and verification
consumers; a host protocol change has RTL consumers. Keeping those relationships
visible mattered more than making every discipline use the same language.
Build logs belonged to the working attempt, while concise verification evidence
belonged in the PR. A clean main checkout was the integration point.

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

### The useful capabilities were a stack

| Capability | What it made possible |
|---|---|
| UART loading and complete readback | Transfer a built ROM, verify its bytes, then start it on the board. |
| UART execution and input controls | Pause, advance execution and apply Game Boy button behavior from the host. |
| Memory and live-register inspection | Inspect software state and hardware-facing registers without a camera. |
| Full pixel capture | Read the rendered frame, independently of what the game says its state should be. |
| Shared build entry points | Build software, run verification and postprocessing, and drive FPGA compilation and board operations. |
| Original game and art tools | Turn assembly, shade grids and placement maps into ROMs and reviewable assets. |
| Phone viewer and command history | Observe actual FPGA pixels remotely and see which button requests were queued or executed. |

Changing games did not inherently mean recompiling and reprogramming the FPGA.
With a compatible hardware image already installed, the host could load another
supported ROM through UART. The
[loader](../tools/n2m/host/SPEC.md) performs begin/write/end, full byte-for-byte
readback and valid/paused checks; running is a separate action. That separation
made trying software iterations practical. It is a controlled cartridge-image
replacement, not overwriting instructions while the CPU executes them.

### RTL: make register intent visible

I cared about the code the agents produced, not only whether a test passed. The
style used explicit module boundaries and package-qualified declarations. For
example, the [CPU](../../src/rtl/cpu/n2m_cpu.sv) declares:

```systemverilog
n2m_cpu_pkg::cpu_execute_request_t execute_request;
n2m_cpu_pkg::cpu_execute_result_t execute_result;
```

The type's owner is visible where it is used, without a wildcard package import
bringing an implicit collection of names into scope. Our register convention
also puts clock, reset and enable behavior into named macros. This actual line
from the [tile decoder](../../src/rtl/display/dmg_tile_pixel.sv) captures the idea:

```systemverilog
`DFF_RST_EN(valid_s1, valid_s0, clk, enable, reset, 1'b0)
```

It is a rising-edge register with reset taking priority over enable. The macro
[definitions](../../src/rtl/common/macros.svh) contain the nonblocking assignments;
product call sites express the register intent instead of repeating the process
boilerplate. Separate forms cover other reset and enable contracts. Assertion
macros provide a similarly consistent way to name simulation checks and fail
when their contracts are violated. This convention was an intentional constraint
on generated code, recorded in the [RTL style](../src/rtl-reference-style.md).

### Memory: simulate the primitive we build

Memory was another place where convenient simulation could have hidden the wrong
hardware contract. The shared
[Intel RAM wrapper](../../src/rtl/common/n2m_intel_ram.sv) instantiates
`altsyncram` with MAX 10 and M9K selected. That instance is compiled for both
Questa, using Intel's installed vendor model, and FPGA synthesis.

Its settings matter: an extra output register would change the consumer's
latency; read/write collisions need an explicit contract; reset does not mean
clearing the entire physical RAM. The wrapper gates requests and validity and
checks illegal overlaps. Simulation preload supplies an initialization file to
the model through a simulation-only parameter path. It does not replace the
memory with a zero-latency Python or SystemVerilog array. Fit and timing checks
still answer the separate question of whether the composed hardware meets its
physical constraints.

### Graphics: build a character from 8×8 tiles

The graphics assets follow the native representation: an 8×8 tile has two bits
per pixel, encoded as two bitplanes, for 16 bytes. Larger characters are composed
from pieces; maps reference shared tiles, with placement and flip information.
That makes reuse explicit rather than storing a full bitmap for every pose or
scene. It also keeps the software close to the graphics hardware it targets.

Our editable art is integer shade JSON plus placement maps. The
[core art pipeline](../src/sw/springtrail/CORE_ART.md) reconstructs the compositions,
and the [software tools](../tools/sw/SPEC.md) encode assets and render preview
sheets. Those sheets let an agent inspect an animation pose, a reused tile or a
mirroring error before integrating it. A shared tile change can affect several
poses, so reviewing the composed character matters as much as reviewing its
individual 8×8 pieces.

![Original character poses and their shared tile maps](../src/sw/springtrail/character-art/small-tile-maps.svg)

*An asset-review diagram, not an FPGA screenshot: composed poses expose how the
8×8 pieces are reused. Editable shade grids and placement maps remain the source.*

![Game artwork from editable tiles to a running ROM](assets/asset-build.svg)

*Asset build path: shade grids and placement maps feed compositions and previews;
encoded two-bitplane tiles are linked with game software into a ROM. The preview
checks artwork, while execution and captured pixels check its integration.*

This compact game representation serves a different purpose from the extra
frame storage used by VGA and remote capture. Reading the actual rendered pixels
provides evidence that parsing the game's intended state alone cannot provide.

![A shared software and verification build session](../showcase/build-and-tests.svg)

*Animated presentation of recorded command output, not a live terminal. The
[session notes](../showcase/README.md#build-and-tests) identify the source and
which output fields were shortened.*

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

Python DV was a meaningful pivot because it connected verification to tools we
could reuse outside the simulator. The continuous path drove the simulated UART
with the product client; Python could organize stimulus, independent expectations
and result processing. Questa still simulated the RTL and vendor memories. We
changed the way tests drove and observed the design, not the design into a
software emulator. Preloaded execution made functional iteration cheaper, while
real upload/readback tests retained responsibility for loading behavior.

The host environment was Windows, with WSL and PowerShell also involved in
remote access and installation. Python environments, tool discovery and the
Questa/Quartus installations were therefore part of reproducibility. The builder
had to identify the tools and inputs actually used, retain a useful failure, and
manage child-process lifetimes. A command that worked in one interactive shell
was not enough for unattended operation from a phone.

> **FIXME (owner input):** Confirm which Windows tools were installed before
> departure and which were installed remotely. Add any specific art-creation
> tool you want credited beyond the repository's shade-grid and preview tools.

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

For me, this was a demonstration of how far AI agents can carry an engineering
project when they can use the whole development stack. They did not stop at
writing modules: they built tools, checked behavior, reviewed changes, deployed
to hardware and exposed the result for remote interaction. My contribution was
direction and engineering judgment throughout that process.

The payoff was wonderfully concrete: a game running on the FPGA at home, its
pixels arriving on my phone, and my button presses travelling back to it. The
same phone that I had used to direct the work became the way I could play it.

---

*Written with AI assistance from the owner's firsthand account and dated
repository evidence. Personal subscription, model-label and rough day-count
recollections are attributed above; technical measurements link to their
producing records. The article records the project on 13 September 2026 and does
not replace current specifications.*
