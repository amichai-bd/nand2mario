# Authoring examples

## Reference study

The frog-bui reference was inspected at immutable revision
`82a6afbf3a72ae4a326ac57b22bb2dc7b556ffae`:

- [Chip design deck](https://github.com/amichai-bd/frog-bui/blob/82a6afbf3a72ae4a326ac57b22bb2dc7b556ffae/wiki/presentations/frog-chip-design.html)
  uses large claim headings and dominant diagrams across disciplines.
- [VGA architecture deck](https://github.com/amichai-bd/frog-bui/blob/82a6afbf3a72ae4a326ac57b22bb2dc7b556ffae/wiki/presentations/frog-vga-architecture.html)
  follows one character/pixel through coordinates, storage and timing, then
  reassembles its journey. Presenter guides define terms and prepare transitions.
- [Series styling](https://github.com/amichai-bd/frog-bui/blob/82a6afbf3a72ae4a326ac57b22bb2dc7b556ffae/wiki/presentations/assets/frog-presentation-series.css)
  uses a dark canvas, discipline accents, compact evidence links and consistent
  controls. These are process ideas, not a code or asset reuse grant.

The [educational series](../../../../wiki/presentations/README.md) applies these
ideas with original content and SVG using the existing nand2mario engine. A dark
surface alone is insufficient: teach a question, concrete example, consequence
and evidence boundary.

## Worked choices

The [CPU deck](../../../../wiki/presentations/cpu-execution.html) follows a NOP
through startup and retirement, then contrasts JP's architectural PC with its
internal cursor. The actual dot schedule teaches a trap that an abstract list of
fetch/decode/execute would miss.

The [graphics deck](../../../../wiki/presentations/graphics-pipeline.html) derives
shades from bitplanes, then maps a coordinate into a VGA block. These are original
explanatory calculations of linked rules, not copied renderer code. The
[software deck](../../../../wiki/presentations/springtrail-software.html) labels
movement as planned while identifying the delivered foundation.

Match visuals to relationships: timeline for overlapping events, converging
arrows for aliases, sequence diagram for retries, calculation for bitplanes.
Repeating generic boxes hides those distinctions. Optional reasoning panels
retain definitions and likely questions without crowding the main claim.

## Validation and publication lessons

Stage new decks and assets before checking: the build discovers tracked files.
Keep generated output and browser evidence in the owning worktree's `workdir/`.
The shared browser suite covers the shell and scaffold example; supplement it
with every new deck's first/last and keyboard navigation, source overlay,
standalone links, fullscreen, expanded reasoning and narrow layout.

Inspect every slide for overflow and tiny labels. Stack short flows. Detailed
diagrams may use a labelled horizontal scroll region that keyboard users can
focus, without making the whole page overflow. Link to a normal section fragment
and set the matching `data-line` for the embedded viewer; always linking line 1
makes readers search the contract again.

Record local generation, hosted checks and actual publication separately. During
this series' delivery, the existing Pages run was externally blocked before
execution by an account condition. This observation justifies inspecting workflow
annotations; it cannot establish publication of new decks. The PR owns the final
delivery result rather than this reusable skill storing live status.

Bad examples: pasted RTL, bitmap diagrams, planned mechanics described as
implemented, copied slide engines, or local generation reported as deployment.
