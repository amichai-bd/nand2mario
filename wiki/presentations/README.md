# Presentations

Explore eight short lessons connecting development concepts to this project.
Each deck has six slides, worked examples, editable diagrams, source links and
expandable reasoning. Read them in order or choose a discipline.

| Lesson | Question | Project connection |
|---|---|---|
| [01 · CPU execution](cpu-execution.html) | When is an instruction complete? | NOP/JP timing, bus commit and retirement |
| [02 · Memory buses](memory-buses.html) | Who owns an addressed byte? | WRAM echo, peripheral decoding and shared storage |
| [03 · Clocks and CDC](clocks-and-cdc.html) | How do different clocks cooperate? | Fractional enables, deadlines and frame ownership |
| [04 · Graphics](graphics-pipeline.html) | How does a tile bit reach VGA? | Shades, complete frames and 3× scaling |
| [05 · UART debugging](uart-debugging.html) | What makes a retry safe? | Packet validation, cached replies and loading |
| [06 · Verification](verification.html) | How do we know a checker works? | Independent oracles, fault injection and bounded evidence |
| [07 · Reproducible builds](reproducible-builds.html) | What does a cached PASS mean? | Input identity, artifact integrity and publication |
| [08 · Original software](springtrail-software.html) | Where does gameplay belong? | Springtrail's ROM and planned deterministic movement |

Use Left/Right or the buttons to navigate; Home/End jump to the first/last slide.
Open **Explore the reasoning** for definitions and discussion prompts. Detailed
wide diagrams scroll horizontally on small screens; simpler flows stack.
Source links open canonical documentation in the embedded wiki viewer.

These decks explain linked contracts; they do not replace them. Springtrail's
foundation is implemented while later gameplay and physical acceptance remain
planned in its source specification.

For authoring, use the [presentation skill](../../.agents/skills/html-presentation/SKILL.md).
The [scaffold tour](scaffold-tour.html) introduces the wiki's source navigation.

## Shared behavior

Link `tools/wiki/assets/tokens.css`, `presentation.css`, and `presentation.js`
with paths relative to the deck. These files own fonts, colors, spacing, and
controls. Do not copy them into each deck. Use HTML/CSS/JavaScript and SVG only;
binary images, fonts, Office files, and PDFs are not presentation sources.

Each `section[data-slide]` is one slide with a heading. The 16:9 canvas fits wide
screens and grows vertically on narrow screens so text remains readable.
Previous/next buttons, Left/Right, Home/End, and a progress label navigate.
Controls keep keyboard focus; slide headings receive focus after keyboard
navigation. Motion respects the reduced-motion preference. Without JavaScript,
all slides remain readable. Escape exits fullscreen through browser controls.

The fullscreen button requests `n2m:fullscreen` from the wiki shell when embedded;
the shell includes its source overlay. If the browser requires a direct gesture,
use the shell's Fullscreen button. Alone, the deck uses the browser
Fullscreen API and reports when it is unavailable.

## Source references

Use an ordinary repository-relative link plus a repository-root source path:

```html
<a href="../../src/rtl/README.md" data-source="src/rtl/README.md" data-line="1">
  Inspect the RTL directory
</a>
```

For published documentation, the shared runtime asks the parent wiki to show
that file with the message
`{type: 'n2m:source', path, line}`. The shell accepts known published files from
its active sandboxed frame. Messages target the parent with `*` because the
frame has an opaque origin; their payload contains only a public source path.
For excluded implementation and helper files, the build converts the reference
to a GitHub link with its line fragment and removes popup attributes. Repository
access is required; no implementation payload is published. Link tracked
sources instead of maintaining code copies on slides.
The [wiki contract](../tools/wiki/SPEC.md) owns publication and source-viewer behavior.
