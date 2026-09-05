# Presentations

Presentations are editable HTML decks under this directory. Use the
[authoring skill](../../.agents/skills/html-presentation/SKILL.md) and
[scaffold tour](scaffold-tour.html).

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

The shared runtime asks the parent wiki to show that file with the message
`{type: 'n2m:source', path, line}`. The shell accepts known published files from
its active sandboxed frame. Messages target the parent with `*` because the
frame has an opaque origin; their payload contains only a public source path.
The ordinary link is the standalone fallback. Link tracked
sources instead of maintaining code copies on slides.
The [wiki contract](../tools/wiki.md) owns publication and source-viewer behavior.
