#!/usr/bin/env python3
"""Draw the measured modules as the committed RTL explorer page.

Block area comes only from the measurements in tools/wiki/rtl_modules.py: a
module's own line count and its register-macro count. The repository retains no
fit report, so no cell, ALM or fitted-register figure is drawn, estimated or
implied anywhere on the page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path
import posixpath

from tools.wiki.rtl_modules import (
    BOARD_TOP, Module, ROOT, RTL, composition, packages, simulation_model,
    specification, stub, tracked)


# Two measured quantities set a block's area: the module's own line count and
# its register-macro count. No cell, ALM or fitted-register figure exists in
# this repository, so none is shown, estimated or implied. The register
# coefficient is a drawing choice, stated on the page so a reader can discount
# it; the line count alone would hide a dense 60-line state machine.
WEIGHT_REGISTER = 4
AREA_PER_UNIT = 140       # square pixels per weight unit, the same in every diagram
HEADER = 19               # label band a parent reserves for its own name
PAD = 3                   # inset between a parent and its children


@dataclass
class Tile:
    module: str
    instance: str
    kind: str              # "module", "own" or "reference"
    weight: float
    children: list["Tile"] = field(default_factory=list)


def own_weight(module: Module) -> int:
    return module.lines + WEIGHT_REGISTER * module.registers


def build(modules: dict[str, Module], name: str, instance: str, earlier: set[str]) -> Tile:
    """The tile for one instance, with a child tile for every instance inside it.

    Inside one diagram every instance is expanded, however often its module
    appears. A module an earlier diagram already expanded is drawn once more as
    a collapsed reference, so the same subtree is never drawn twice.
    """
    module = modules[name]
    own = own_weight(module)
    inside = [i for i in module.instances if i.view in ("both", "synthesis")]
    if not inside:
        return Tile(name, instance, "module", own)
    if name in earlier:
        return Tile(name, instance, "reference", own)
    children = [Tile(name, instance, "own", own)]
    children += [build(modules, i.module, i.name, earlier) for i in inside]
    return Tile(name, instance, "module", sum(c.weight for c in children), children)


def squarify(values: list[float], x: float, y: float, width: float, height: float):
    """Squarified treemap rectangles, one per value, in the values' own order."""
    rects: list[tuple[float, float, float, float]] = [(x, y, 0.0, 0.0)] * len(values)
    total = sum(values)
    if total <= 0 or width <= 0 or height <= 0:
        return rects
    order = sorted(range(len(values)), key=lambda i: -values[i])
    scale = width * height / total
    areas = [values[i] * scale for i in order]
    left, top, free_w, free_h = x, y, width, height
    start = 0
    while start < len(areas):
        side = min(free_w, free_h)

        def ratio(row: list[float]) -> float:
            thickness = sum(row) / side
            return max(max(thickness / (a / thickness), (a / thickness) / thickness)
                       for a in row if a > 0) if thickness > 0 else float("inf")

        row, end = [areas[start]], start + 1
        while end < len(areas) and areas[end] > 0 and ratio(row + [areas[end]]) <= ratio(row):
            row.append(areas[end])
            end += 1
        thickness = sum(row) / side
        offset = 0.0
        for position, area in enumerate(row):
            length = area / thickness if thickness else 0.0
            if free_h <= free_w:
                rects[order[start + position]] = (left, top + offset, thickness, length)
            else:
                rects[order[start + position]] = (left + offset, top, length, thickness)
            offset += length
        if free_h <= free_w:
            left, free_w = left + thickness, free_w - thickness
        else:
            top, free_h = top + thickness, free_h - thickness
        start = end
    return rects


def place(tile: Tile, x: float, y: float, width: float, height: float, depth: int):
    """Flatten a tile tree into (tile, rect, depth) in drawing order."""
    placed = [(tile, (x, y, width, height), depth)]
    if not tile.children:
        return placed
    inner_x, inner_y = x + PAD, y + HEADER
    inner_w, inner_h = width - 2 * PAD, height - HEADER - PAD
    rects = squarify([c.weight for c in tile.children], inner_x, inner_y, inner_w, inner_h)
    for child, rect in zip(tile.children, rects):
        placed += place(child, *rect, depth + 1)
    return placed


def classes(tile: Tile, module: Module) -> str:
    names = ["t-" + {"module": "module", "own": "own", "reference": "ref"}[tile.kind]]
    if stub(module):
        names.append("t-stub")
    if simulation_model(module.name):
        names.append("t-sim")
    return " ".join(names)


def outsiders(modules: dict[str, Module], shown: list[str]) -> str:
    """One sentence naming the instantiated modules this repository does not hold."""
    names = sorted({instance.module for name in shown for instance in modules[name].vendor})
    if not names:
        return ""
    return (f" {len(names)} instantiated module{'s are' if len(names) != 1 else ' is'} not in "
            "this repository — " + ", ".join(names) + " — each a vendor primitive or a "
            "Quartus-generated component. They are named on their parent blocks and none is "
            "drawn, because there is nothing here to measure.")


def counts(module: Module) -> str:
    registers = "no registers" if not module.registers else (
        f"{module.registers} register" + ("s" if module.registers != 1 else ""))
    return f"{module.lines} lines · {registers}"


def label(tile: Tile, module: Module) -> list[tuple[str, str]]:
    """(css class, text) per label line, longest first, before any fit test."""
    if tile.kind == "own":
        return [("n", "own logic"),
                ("f", f"{module.lines} L · {module.registers} R" if module.registers
                 else f"{module.lines} L · structural")]
    lines = [("n", tile.instance)] if tile.instance != module.name else []
    lines.append(("m", module.name))
    if tile.kind == "reference":
        lines.append(("f", "expanded above"))
    else:
        lines.append(("f", f"{module.lines} L · {module.registers} R"))
    if module.vendor:
        lines.append(("v", "+ " + ", ".join(sorted({v.module for v in module.vendor}))))
    return lines


def fits(text: str, width: float) -> bool:
    return len(text) * 6.4 + 10 <= width


def shortest(text: str, width: float) -> str | None:
    """The text, or its unprefixed form when the full name will not fit, or None."""
    if fits(text, width):
        return text
    trimmed = text.replace("n2m_", "", 1)
    return trimmed if trimmed != text and fits(trimmed, width) else None


def svg_tile(tile: Tile, rect, module: Module) -> str:
    x, y, width, height = rect
    target = html_escape("#m-" + module.name)
    title = f"{tile.instance}: {module.name} — {counts(module)}"
    parts = [f'<a href="{target}" class="{classes(tile, module)}" '
             f'data-module="{html_escape(module.name)}">',
             f'<title>{html_escape(title)}</title>',
             f'<rect x="{round(x, 1)}" y="{round(y, 1)}" width="{round(width, 1)}" '
             f'height="{round(height, 1)}" rx="4" />']
    if tile.children:
        head = f"{tile.instance} : {module.name}" if tile.instance != module.name else module.name
        head = f"{head} · {module.lines} L · {module.registers} R"
        head = shortest(head, width) or shortest(module.name, width)
        if head:
            parts.append(f'<text class="h" x="{round(x + 7, 1)}" y="{round(y + 13.5, 1)}">'
                         f'{html_escape(head)}</text>')
    else:
        shown = [(kind, shortest(text, width)) for kind, text in label(tile, module)]
        shown = [(kind, text) for kind, text in shown if text]
        while shown and len(shown) * 13 + 6 > height:
            shown.pop()
        top = y + height / 2 - (len(shown) - 1) * 6.5
        for position, (kind, text) in enumerate(shown):
            parts.append(f'<text class="{kind}" x="{round(x + width / 2, 1)}" '
                         f'y="{round(top + position * 13 + 4, 1)}">{html_escape(text)}</text>')
    parts.append("</a>")
    return "".join(parts)


def diagram(tiles: list[Tile], modules: dict[str, Module], width: int, label_text: str) -> tuple[str, list[str]]:
    """The SVG for these roots, and the module names it draws in drawing order."""
    total = sum(t.weight for t in tiles)
    height = max(120, round(total * AREA_PER_UNIT / width))
    if len(tiles) == 1:
        placed = place(tiles[0], 0, 0, width, height, 0)
    else:
        placed = []
        for tile, rect in zip(tiles, squarify([t.weight for t in tiles], 0, 0, width, height)):
            placed += place(tile, *rect, 0)
    body = "".join(svg_tile(tile, rect, modules[tile.module]) for tile, rect, _ in placed)
    drawn: list[str] = []
    for tile, _, _ in placed:
        if tile.module not in drawn:
            drawn.append(tile.module)
    svg = (f'<svg class="rtl-map" viewBox="0 0 {width} {height}" style="min-width:{width}px" '
           f'role="img" aria-label="{html_escape(label_text)}">{body}</svg>')
    return svg, drawn


# --- Page ------------------------------------------------------------------
PAGE = "wiki/presentations/rtl-explorer.html"
STYLESHEET = "wiki/presentations/assets/rtl-explorer.css"
SCRIPT = "wiki/presentations/assets/rtl-explorer.js"


def relative(target: str, source: str = PAGE) -> str:
    return posixpath.relpath(target, posixpath.dirname(source))


def source_link(module: Module, text: str) -> str:
    return (f'<a href="{html_escape(relative(module.path))}" data-source="{html_escape(module.path)}" '
            f'data-line="{module.line}">{html_escape(text)}</a>')


def ports_html(module: Module) -> str:
    if not module.ports:
        return '<p class="none">No ports.</p>'
    short = {"input": "in", "output": "out", "inout": "inout", "ref": "ref"}
    items = "".join(
        f'<li><b>{short.get(port.direction, port.direction)}</b> '
        f'<code>{html_escape(port.kind)}</code> {html_escape(port.name)}</li>'
        for port in module.ports)
    return f'<ul class="ports">{items}</ul>'


def panel(module: Module, parents: list[tuple[str, str, str]]) -> str:
    facts = [f'<code>{html_escape(module.path)}</code>',
             f"{module.lines} lines",
             (f"{module.registers} register macro" + ("s" if module.registers != 1 else ""))
             if module.registers else "no registers of its own",
             f"{len(module.ports)} ports"]
    if module.register_macros:
        facts.append(", ".join(f"<code>{name}</code>&nbsp;×{count}" for name, count
                               in sorted(module.register_macros.items())))
    if module.simulation_registers:
        facts.append(f"{module.simulation_registers} more registers in a simulation-only branch")
    if module.raw_processes:
        facts.append(f"{module.raw_processes} behavioural <code>always</code> blocks "
                     "outside the register macros")
    if not module.instances and not module.registers and not module.vendor:
        facts.append("combinational: no registers and no submodules")
    told = (html_escape(module.summary) if module.summary else
            "This module carries no comment above its declaration; its subsystem contract is "
            "linked below.")
    detail = [f'<p class="tldr">{told}</p>',
              '<p class="facts">' + " · ".join(facts) + "</p>"]
    inside = []
    for instance in module.instances:
        note = "" if instance.view in ("both", "synthesis") else " (simulation branch only)"
        inside.append(f'{html_escape(instance.name)} : <a href="#m-{html_escape(instance.module)}">'
                      f'{html_escape(instance.module)}</a>{note}')
    for instance in module.vendor:
        inside.append(f"{html_escape(instance.name)} : {html_escape(instance.module)} "
                      "(vendor primitive, not in this repository)")
    if inside:
        detail.append('<p class="rel"><b>Contains</b> ' + "; ".join(inside) + "</p>")
    if parents:
        held = "; ".join(
            f'<a href="#m-{html_escape(name)}">{html_escape(name)}</a> as {html_escape(instance)}'
            + ("" if view in ("both", "synthesis") else " (simulation branch only)")
            for name, instance, view in parents)
        detail.append(f'<p class="rel"><b>Instantiated by</b> {held}</p>')
    specification_path = specification(module)
    detail.append('<p class="links">'
                  + source_link(module, f"Open {module.path.rsplit('/', 1)[1]} at line {module.line}")
                  + f' · <a href="{html_escape(relative(specification_path))}">Specification: '
                  + html_escape(specification_path.rsplit("/", 1)[1]) + "</a></p>")
    detail.append(ports_html(module))
    badge = ""
    if stub(module):
        badge = '<span class="badge stub">present, unimplemented</span>'
    elif simulation_model(module.name):
        badge = '<span class="badge sim">simulation model</span>'
    return (f'<details id="m-{html_escape(module.name)}" class="module" open>'
            f'<summary><b>{html_escape(module.name)}</b>'
            f'<span class="tag">{html_escape(counts(module))}</span>{badge}</summary>'
            + "".join(detail) + "</details>")


def panels(modules: dict[str, Module], names: list[str], parents: dict[str, list]) -> str:
    return ('<div class="panels" data-scroll-region tabindex="0" role="region" '
            'aria-label="Module details; one panel for every block in the diagram above">'
            + "".join(panel(modules[name], parents.get(name, [])) for name in names) + "</div>")


def legend() -> str:
    """The four block kinds, drawn with the same classes the diagrams use."""
    entries = [("t-module", "u_ppu : n2m_ppu", "an instance of an implemented module"),
               ("t-own", "own logic", "what the parent itself holds, beside its children"),
               ("t-module t-stub", "u_apu : n2m_apu", "present, but unimplemented"),
               ("t-module t-sim", "n2m_sim_sdram", "a simulation stand-in, never synthesized"),
               ("t-ref", "n2m_v05_system", "already expanded in an earlier diagram")]
    parts = []
    for position, (kind, name, meaning) in enumerate(entries):
        top = position * 46
        parts.append(f'<g class="{kind}"><rect x="1" y="{top + 4}" width="210" height="38" rx="4" />'
                     f'<text class="m" x="106" y="{top + 27}">{html_escape(name)}</text></g>'
                     f'<text class="legend" x="226" y="{top + 28}">{html_escape(meaning)}</text>')
    return (f'<svg class="rtl-legend" viewBox="0 0 760 {len(entries) * 46 + 8}" role="img" '
            f'aria-label="Block kinds: implemented instance, own logic, present but '
            f'unimplemented, simulation model, and a collapsed reference">'
            + "".join(parts) + "</svg>")


def slide(number: int, total: int, eyebrow: str, heading: str, body: str, tag: str = "h2") -> str:
    return (f'<section data-slide aria-labelledby="slide-{number}">'
            f'<p class="eyebrow">{html_escape(eyebrow)} · {number:02d} / {total:02d}</p>'
            f'<{tag} id="slide-{number}">{html_escape(heading)}</{tag}>{body}</section>')


def facts(modules: dict[str, Module], root: Path = ROOT) -> dict[str, int]:
    sources = tracked(root, RTL)
    lines = {path: len((root / path).read_text(encoding="utf-8").splitlines()) for path in sources}
    library = {name: module for name, module in modules.items() if module.path.startswith(RTL)}
    declared = sum(lines[module.path] for module in library.values())
    return {"files": len(sources), "lines": sum(lines.values()),
            "modules": len(library), "module_lines": declared,
            "packages": len(sources) - len(library),
            "package_lines": sum(lines.values()) - declared,
            "registers": sum(module.registers for module in library.values()),
            "ports": sum(len(module.ports) for module in library.values()),
            "owners": len(modules["n2m_v05_system"].instances)}


def document(root: Path = ROOT) -> str:
    modules = composition(root)
    numbers = facts(modules, root)
    parents: dict[str, list[tuple[str, str]]] = {}
    for name, module in sorted(modules.items()):
        for instance in module.instances:
            parents.setdefault(instance.module, []).append((name, instance.name, instance.view))

    board = build(modules, BOARD_TOP, BOARD_TOP, set())
    composed, shown = diagram([board], modules, 1100,
                              "The DE10-Lite composition: every module instance drawn inside "
                              "the module that instantiates it, sized by measured lines and registers")
    rest = [name for name in modules if name not in shown]
    roots = [name for name in rest if not any(
        parent in rest and view in ("both", "synthesis")
        for parent, _, view in parents.get(name, []))]
    others = [build(modules, name, name, set(shown)) for name in roots]
    outside, drawn_again = diagram(others, modules, 900,
                            "Modules under src/rtl/ that the composed board design does not "
                            "instantiate: the physical-control top, and the simulation models")
    also = [name for name in drawn_again if name not in shown]
    missing = [name for name in modules if name not in shown and name not in also]
    if missing:
        raise ValueError(f"Modules absent from both diagrams: {missing}")

    intro = (
        '<p class="lead">This page draws the composed DE10-Lite design as nested blocks. '
        'One block is one module instance; a block inside another block is instantiated there. '
        'Select any block to read what that module owns, its ports, and its real source.</p>'
        '<div class="comparison">'
        '<div><strong>Measured</strong><p>Lines per file, register-macro invocations, ports with '
        'direction and width, and the instance tree — all read from the SystemVerilog by '
        '<code>tools/wiki/rtl_modules.py</code>.</p></div>'
        '<div><strong>Sets a block\'s size</strong><p>Its area follows '
        '<code>lines + 4 × register macros</code>, and nothing else. The coefficient is a drawing '
        'choice; the two counts are measurements.</p></div>'
        '<div><strong>Not here</strong><p>No cell, ALM or fitted-register figure. The repository '
        'keeps no fit report, and a whole-design fit cannot be divided back into modules. Rather '
        'than estimate one, this page shows none.</p></div>'
        '</div>'
        f'<p><code>src/rtl/</code> holds {numbers["files"]} tracked SystemVerilog files and '
        f'{numbers["lines"]:,} lines: {numbers["modules"]} modules ({numbers["module_lines"]:,} '
        f'lines, {numbers["registers"]} register macros, {numbers["ports"]:,} ports) and '
        f'{numbers["packages"]} packages ({numbers["package_lines"]:,} lines). '
        f'<code>n2m_v05_system</code> instantiates {numbers["owners"]} owners; several are '
        'themselves structural, so the shape below is a tree rather than a row.</p>'
        '<details><summary>Explore the reasoning</summary><p>Searching for <code>always_ff</code> '
        'would report zero registers for most of these modules. Every flop here is declared '
        'through a macro in <code>src/rtl/common/macros.svh</code>, so the macro invocations are '
        'the measurement. They are counted in the synthesis view, with <code>SYNTHESIS</code> '
        'defined, so a simulation-only branch is reported separately instead of being counted as '
        'hardware.</p></details>'
        '<p class="sources">'
        + source_link(modules["n2m_v05_system"], "Source: n2m_v05_system.sv")
        + ' · <a href="../src/rtl/system/MAS_system.md">Source: the system composition contract</a>'
        + ' · <a href="../../src/rtl/common/macros.svh" data-source="src/rtl/common/macros.svh" '
          'data-line="5">Source: the register macros</a></p>')

    reading = (
        f'<p class="lead">A parent block holds its children plus one <em>own logic</em> tile. That '
        'tile is the parent\'s own lines and registers — the wiring and arbitration it does '
        'itself — so a structural module reads as a thin frame around its children instead of '
        'an empty box.</p>'
        + legend() +
        '<p>A panel\'s summary is the comment the source carries above that module, or at the '
        'head of its file. Where that comment records provenance rather than behaviour, that is '
        'what the source says; the linked contract carries the behaviour. '
        f'{sum(1 for module in modules.values() if not module.summary)} modules carry no comment '
        'at all, and their panels say so instead of inventing one.</p>'
        '<p>Areas are exact within one parent. Each parent also spends a label band and a small '
        'inset on its frame, so a deeply nested block is drawn a little smaller than a block of '
        'the same weight near the top. Compare siblings confidently; compare across depths '
        'loosely. A name that will not fit its block loses its <code>n2m_</code> prefix, and '
        'then the block carries no label at all; its panel and its hover text always carry the '
        'full name.</p>'
        '<details><summary>Explore the reasoning</summary><p>A worked size: '
        f'<code>n2m_ppu_timing</code> is {modules["n2m_ppu_timing"].lines} lines with '
        f'{modules["n2m_ppu_timing"].registers} register macros, so its weight is '
        f'{own_weight(modules["n2m_ppu_timing"])}. <code>n2m_cpu_execute</code> is '
        f'{modules["n2m_cpu_execute"].lines} lines with {modules["n2m_cpu_execute"].registers} '
        f'registers, so its weight is {own_weight(modules["n2m_cpu_execute"])}. The longer file '
        'draws larger even though it holds no state, which is the honest reading of the two '
        'measurements: one is a wide combinational decode, the other a dense sequencer.</p>'
        '</details>'
        '<p class="sources"><a href="../src/rtl-reference-style.md">Source: the RTL reference '
        'style</a></p>')

    machine = (
        '<p class="lead">The root is <code>v05_proof</code>, the composed DE10-Lite top. Scroll '
        'the diagram sideways on a narrow screen; select a block to open its panel below.</p>'
        '<div class="diagram-scroll" data-scroll-region tabindex="0" role="region" '
        'aria-label="The composed module tree; scroll horizontally on a narrow screen">'
        + composed + '</div>'
        f'<p class="diagram-caption">{len(shown)} modules, drawn at every instance.'
        + outsiders(modules, shown) + '</p>'
        + panels(modules, shown, parents))

    remainder = (
        '<p class="lead">These modules are under <code>src/rtl/</code> but the composed board '
        'design does not instantiate them. <code>n2m_controls_system</code> is the variant top '
        'that swaps in the physical-control producer; the <code>n2m_sim_*</code> models stand in '
        'for vendor primitives under simulation only.</p>'
        '<div class="diagram-scroll" data-scroll-region tabindex="0" role="region" '
        'aria-label="Modules outside the composed design; scroll horizontally on a narrow screen">'
        + outside + '</div>'
        '<p class="diagram-caption">Drawn at the same scale as the composition above.'
        + outsiders(modules, also) + '</p>'
        + panels(modules, also, parents)
        + '<h3>Packages are not blocks</h3>'
        f'<p>{numbers["packages"]} of the {numbers["files"]} files under <code>src/rtl/</code> are '
        'packages. A package declares shared types and constants and is imported, never '
        'instantiated, so it has no place in an instance tree and none is drawn. They are listed '
        'here with their sizes instead.</p>'
        + '<ul class="packages">' + "".join(
            f'<li><a href="{html_escape(relative(path))}" data-source="{html_escape(path)}" '
            f'data-line="1"><code>{html_escape(name)}</code></a> · {count} lines'
            + (f' · {html_escape(text.split(". ")[0].rstrip("."))}.' if text else "") + "</li>"
            for name, path, count, text in packages(root)) + "</ul>")

    limits = (
        '<p class="lead">Two boards are supported. The DE10-Lite (MAX 10 '
        '<code>10M50DAF484C7G</code>) is the qualified board: the tree above is rooted at its '
        'composed top and its bring-up is recorded. DE10-Nano (Cyclone V SE '
        '<code>5CSEBA6U23I7</code>) support is in progress; no DE10-Nano top exists in the tree '
        'yet, so none is drawn here.</p>'
        '<div class="comparison">'
        '<div><strong>Generated, not written</strong><p><code>tools/wiki/rtl_modules.py</code> '
        'measures the sources and <code>tools/wiki/rtl_explorer.py</code> draws this page. A host '
        'test rebuilds it and fails when the committed page differs, so the diagram cannot drift '
        'away from the RTL.</p></div>'
        '<div><strong>Counted in the synthesis view</strong><p>Registers and instances are read '
        'with <code>SYNTHESIS</code> defined. Simulation-only registers and instances are named '
        'in the panels rather than counted as hardware.</p></div>'
        '<div><strong>Still open</strong><p>A second board needs its own device targets and its '
        'own clocking evidence: '
        '<a href="https://github.com/amichai-bd/nand2mario/issues/809">issue 809</a> and '
        '<a href="https://github.com/amichai-bd/nand2mario/issues/810">issue 810</a>.</p></div>'
        '</div>'
        '<details><summary>Explore the reasoning</summary><p>A per-module cell count would answer '
        'a different question than this page does, and answering it would mean synthesising each '
        'module alone — a figure that would not match what the whole design fits to. Line and '
        'register counts are cheap, exact, and recomputed on every check. Where they mislead, the '
        'panel says so: a wide combinational decode is long and holds nothing.</p></details>'
        '<p class="sources"><a href="../src/board-bring-up.md">Source: board bring-up</a> · '
        '<a href="../src/rtl/system/MAS_system.md">Source: the system composition contract</a> · '
        '<a href="../tools/wiki/SPEC.md">Source: the wiki build contract</a></p>')

    slides = [slide(1, 5, "RTL explorer", "Every module, inside the one that builds it", intro, "h1"),
              slide(2, 5, "RTL explorer", "How to read a block", reading),
              slide(3, 5, "RTL explorer", "The composed machine", machine),
              slide(4, 5, "RTL explorer", "Outside that composition", remainder),
              slide(5, 5, "RTL explorer", "What this page does not claim", limits)]
    return ('<!doctype html>\n<html lang="en">\n<head>\n  <meta charset="utf-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '  <title>RTL module explorer</title>\n'
            '  <link rel="stylesheet" href="../../tools/wiki/assets/presentation.css">\n'
            '  <link rel="stylesheet" href="assets/concepts.css">\n'
            f'  <link rel="stylesheet" href="{relative(STYLESHEET)}">\n'
            '  <script src="../../tools/wiki/assets/presentation.js" defer></script>\n'
            f'  <script src="{relative(SCRIPT)}" defer></script>\n'
            '</head>\n<body class="concept-series rtl">\n'
            '  <main class="deck" aria-label="RTL module explorer">\n'
            '    <a class="series-home" href="README.md">← Presentation library</a>\n    '
            + "\n    ".join(slides)
            + '\n  </main>\n</body>\n</html>\n')


def write(root: Path = ROOT) -> Path:
    """Rewrite the committed page from the current sources."""
    target = root / PAGE
    target.write_text(document(root), encoding="utf-8")
    return target


if __name__ == "__main__":
    print(write())
