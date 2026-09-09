---
name: html-presentation
description: Create or revise interactive HTML presentations for the nand2mario wiki, using shared styling and clickable source references. Use for repository slide decks, not Office or PDF output.
---

# HTML presentation

1. Read [the presentation contract](../../../wiki/presentations/README.md).
2. Read canonical topic contracts and evidence before outlining. Choose one
   worked journey: an instruction, pixel, command, build or game update. Separate
   implemented behavior, planned rules and physical proof on the slides.
3. Start from [the template](templates/deck.html). Save under `wiki/presentations/`,
   adjust relative assets and update the index. Use the
   [reference and authoring examples](examples/authoring.md) for narrative and
   layout techniques without copying reference code or assets.
4. Give each slide one claim and a dominant editable SVG, calculation or
   comparison. Put definitions and discussion in optional `details` panels.
   Link canonical sections with matching source-viewer line numbers. Explain
   examples without mirroring the specification.
5. Reuse shared tokens, styles and runtime. A series stylesheet may extend layout,
   but must not create another engine. Stack simple diagrams on small screens;
   keep detailed diagrams legible in labelled keyboard-scroll regions.
6. Stage new files, then run `python tools/wiki/check.py --browser` (add
   `--install-browser` for first-time pinned setup). Inspect every new deck,
   embedded and standalone: navigation, focus, source links, fullscreen, reasoning
   panels, narrow layouts and console errors. Save visual evidence under the
   author worktree's `workdir/`; the generic suite does not visually review all slides.
7. Use normal reviewed PR delivery. Verify the actual Pages workflow and served
   revision after merge. Local generation does not deploy; report externally
   blocked Pages jobs honestly.

See [the examples](examples/authoring.md) for scope and a working deck. Report
the actual checks and limits. Stop if the deck needs an undecided product
contract; do not invent architecture to complete a presentation.
