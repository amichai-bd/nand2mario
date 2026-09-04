---
name: html-presentation
description: Create or revise interactive HTML presentations for the nand2mario wiki, using shared styling and clickable source references. Use for repository slide decks, not Office or PDF output.
---

# HTML presentation

1. Read [the presentation contract](../../../wiki/presentations/README.md).
2. Start from [the template](templates/deck.html). Save the deck under
   `wiki/presentations/`; adjust relative asset links for its location.
3. Use one clear point per slide. Link to existing sources instead of copying
   their content. Keep diagrams editable as SVG.
4. Reuse the shared styles and runtime. Do not invent another slide engine.
5. Stage new files and run `python tools/wiki/check.py`. Inspect the embedded
   and standalone deck: keyboard, small screen, source link, and fullscreen.

See [the examples](examples/authoring.md) for scope and a working deck. Report
the actual checks and limits. Stop if the deck needs an undecided product
contract; do not invent architecture to complete a presentation.
