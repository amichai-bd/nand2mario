#!/usr/bin/env python3
"""Measure src/rtl/ and generate the committed RTL explorer page.

Every number the explorer shows is read from the SystemVerilog sources here:
file line counts, register-macro invocations, ports and instances. Nothing is
estimated, and no synthesis or fit report is consulted, because the repository
retains none and a whole-design fit cannot be attributed to one module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path
import posixpath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
RTL = "src/rtl/"
IDENT = r"[A-Za-z_][A-Za-z0-9_$]*"

# Every flop in this repository is declared through one of these macros
# (src/rtl/common/macros.svh). Searching for `always_ff` instead returns zero on
# a structural module and misses every macro site, so the macro names are the
# measurement. N2M_ASSERT_STABLE_WHEN also expands to a register; it is a
# simulation check, never synthesized, so it is not counted here.
REGISTER_MACROS = (
    "DFF", "DFF_RST", "DFF_RST_VAL", "DFF_EN", "DFF_RST_EN",
    "DFF_ARST_VAL", "DFF_ARST_N_VAL", "DFF_INIT_ARST_VAL", "DFF_INIT_ARST_N_VAL",
)

# Declarations and statements whose head is an identifier followed by another
# identifier and an open paren, which is also the shape of an instantiation.
NOT_INSTANCES = {
    "module", "endmodule", "package", "endpackage", "function", "endfunction",
    "task", "endtask", "typedef", "generate", "endgenerate", "begin", "end",
    "if", "else", "for", "while", "case", "casez", "always", "always_ff",
    "always_comb", "assign", "return", "logic", "bit", "int", "integer", "var",
    "wire", "reg", "byte", "string", "automatic", "static", "localparam",
    "parameter", "input", "output", "inout", "unique", "priority", "posedge",
    "negedge", "initial", "final", "assert", "property", "genvar", "const",
    "signed", "unsigned", "void", "real", "time", "type", "let", "endcase",
    "longint", "shortint", "shortreal", "chandle", "event", "struct", "union",
    "enum", "packed", "do", "forever", "repeat", "break", "continue", "import",
}

# An identifier in one of these positions heads a declaration, never an instance.
NOT_BEFORE = {"function", "task", "automatic", "static", "virtual", "const",
              "typedef", "extern", "import", "export", "localparam", "parameter",
              "input", "output", "inout", "var", "return", "new"}


@dataclass
class Port:
    direction: str
    kind: str
    name: str


@dataclass
class Instance:
    module: str
    name: str
    line: int
    view: str  # "both", "synthesis" or "simulation"


@dataclass
class Module:
    name: str
    path: str
    line: int          # the line the module keyword is on
    lines: int         # physical lines in the file
    summary: str       # the authored comment block above the module keyword
    ports: list[Port] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    registers: int = 0
    register_macros: dict[str, int] = field(default_factory=dict)
    simulation_registers: int = 0
    raw_processes: int = 0
    instances: list[Instance] = field(default_factory=list)
    vendor: list[Instance] = field(default_factory=list)


def tracked(root: Path = ROOT, prefix: str = RTL) -> list[str]:
    """Tracked SystemVerilog sources under a prefix, in sorted order."""
    listed = subprocess.check_output(["git", "ls-files", "-z", prefix], cwd=root)
    return sorted(p for p in listed.decode().split("\0") if p.endswith(".sv"))


def blanked(text: str) -> str:
    """Comments and string literals replaced by spaces; line numbers preserved."""
    out, index, length = [], 0, len(text)
    while index < length:
        char = text[index]
        pair = text[index:index + 2]
        if pair == "//":
            end = text.find("\n", index)
            end = length if end < 0 else end
            out.append(" " * (end - index))
            index = end
        elif pair == "/*":
            end = text.find("*/", index + 2)
            end = length if end < 0 else end + 2
            out.append("".join(c if c == "\n" else " " for c in text[index:end]))
            index = end
        elif char == '"':
            end, index = index + 1, index + 1
            while end < length and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            out.append(" " * (end - index + 2))
            index = min(end + 1, length)
        else:
            out.append(char)
            index += 1
    return "".join(out)


def synthesis_view(text: str) -> list[bool]:
    """Per line, whether it survives the preprocessor with SYNTHESIS defined.

    The board build defines SYNTHESIS and nothing else, so this is the circuit
    the reader is looking at. A simulation-only branch is reported separately
    rather than silently counted as hardware.
    """
    defined = {"SYNTHESIS"}
    active: list[bool] = []
    stack: list[tuple[bool, bool]] = []  # (taken so far, this branch active)
    for line in text.splitlines():
        head = line.strip()
        directive = re.match(r"`(ifdef|ifndef|elsif|else|endif)\b\s*(" + IDENT + ")?", head)
        if directive:
            keyword, name = directive.group(1), directive.group(2)
            if keyword in ("ifdef", "ifndef"):
                take = (name in defined) if keyword == "ifdef" else (name not in defined)
                enclosing = all(branch for _, branch in stack)
                stack.append((take, take and enclosing))
            elif keyword == "elsif" and stack:
                taken, _ = stack[-1]
                take = not taken and name in defined
                enclosing = all(branch for _, branch in stack[:-1])
                stack[-1] = (taken or take, take and enclosing)
            elif keyword == "else" and stack:
                taken, _ = stack[-1]
                enclosing = all(branch for _, branch in stack[:-1])
                stack[-1] = (True, not taken and enclosing)
            elif keyword == "endif" and stack:
                stack.pop()
            active.append(False)
            continue
        active.append(all(branch for _, branch in stack))
    return active


def line_of(text: str) -> "callable":
    """A function from an index in `text` to its 1-based line number."""
    breaks = [match.start() for match in re.finditer("\n", text)]
    import bisect
    return lambda index: bisect.bisect_right(breaks, index - 1) + 1


def split_top(text: str) -> list[str]:
    """Split on commas that are not inside brackets."""
    parts, depth, current = [], 0, []
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def balanced(text: str, start: int) -> int:
    """Index just past the bracket group that opens at `start`."""
    depth, index = 0, start
    while index < len(text):
        if text[index] in "([{":
            depth += 1
        elif text[index] in ")]}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise ValueError("unbalanced group")


def parse_ports(text: str) -> list[Port]:
    """ANSI port headers, including names that inherit the previous direction."""
    ports, direction, kind = [], "", ""
    for item in split_top(text):
        item = re.sub(r"=.*", "", item, flags=re.S).strip()
        item = " ".join(item.split())
        if not item:
            continue
        head = re.match(r"(input|output|inout|ref)\b\s*", item)
        if head:
            direction = head.group(1)
            item = item[head.end():]
            kind = ""
        item = re.sub(r"^var\b\s*", "", item)
        name = re.search(rf"({IDENT})\s*(\[[^\]]*\])?$", item)
        if not name:
            continue
        declared = item[:name.start()].strip()
        if declared:
            kind = declared
        unpacked = name.group(2) or ""
        ports.append(Port(direction or "input", (kind or "logic") + unpacked, name.group(1)))
    return ports


def parse_instances(body: str, offset: int, active: list[bool], known: set[str]) -> tuple[list[Instance], list[Instance]]:
    """Every `<type> [#(...)] <name> [[...]] (` site, by the line it starts on."""
    repo, vendor = [], []
    line_at = line_of(body)
    for match in re.finditer(rf"\b({IDENT})\b", body):
        head = match.group(1)
        if head in NOT_INSTANCES or head.endswith("_pkg"):
            continue
        # A bounded look-back: only the token immediately before matters, and
        # slicing the whole prefix for every identifier is quadratic.
        before = body[max(0, match.start() - 48):match.start()].rstrip()
        if before.endswith("::") or before.endswith("."):
            continue
        previous = re.search(rf"({IDENT})\s*$", before)
        if previous and previous.group(1) in NOT_BEFORE:
            continue
        index = match.end()
        while index < len(body) and body[index] in " \t\r\n":
            index += 1
        if index < len(body) and body[index] == "#":
            index += 1
            while index < len(body) and body[index] in " \t\r\n":
                index += 1
            if index >= len(body) or body[index] != "(":
                continue
            index = balanced(body, index)
            while index < len(body) and body[index] in " \t\r\n":
                index += 1
        name = re.match(rf"({IDENT})", body[index:])
        if not name or name.group(1) in NOT_INSTANCES:
            continue
        index += name.end()
        while index < len(body) and body[index] in " \t\r\n":
            index += 1
        if index < len(body) and body[index] == "[":
            index = balanced(body, index)
            while index < len(body) and body[index] in " \t\r\n":
                index += 1
        if index >= len(body) or body[index] != "(":
            continue
        line = offset + line_at(match.start()) - 1
        view = "synthesis" if active[line - 1] else "simulation"
        target = repo if head in known else vendor
        target.append(Instance(head, name.group(1), line, view))
    return repo, vendor


def summary_comment(lines: list[str], declaration: int) -> str:
    """The comment paragraph a module carries: above its keyword, or at the file head.

    Several sources put the whole description at the top of the file, above the
    compiler directives, so a backwards walk from `module` finds nothing there.
    Only the first paragraph is kept; the rest of a long block is in the file.
    """

    def body(line: str) -> str | None:
        stripped = line.strip()
        if not stripped.startswith("//"):
            return None
        text = stripped[2:].strip()
        return None if text.startswith("SPDX-License-Identifier") else text

    above: list[str] = []
    for previous in reversed(lines[:declaration - 1]):
        text = body(previous)
        if not text:
            break
        above.insert(0, text)
    if above:
        return " ".join(above)
    head: list[str] = []
    for line in lines[:declaration - 1]:
        text = body(line)
        if not text:
            break
        head.append(text)
    return " ".join(head)


def parse_module(path: str, text: str) -> Module | None:
    """The single module a source file declares, or None for a package."""
    clean = blanked(text)
    active = synthesis_view(text)
    header = re.search(rf"^[ \t]*module\s+({IDENT})", clean, re.M)
    if not header:
        return None
    name = header.group(1)
    line = clean[:header.start()].count("\n") + 1
    comment = summary_comment(text.splitlines(), line)
    index = header.end()
    parameters: list[str] = []
    while index < len(clean) and clean[index] in " \t\r\n":
        index += 1
    if index < len(clean) and clean[index] == "#":
        index += 1
        while clean[index] in " \t\r\n":
            index += 1
        end = balanced(clean, index)
        for item in split_top(clean[index + 1:end - 1]):
            found = re.search(rf"({IDENT})\s*=", item) or re.search(rf"({IDENT})\s*$", item)
            if found:
                parameters.append(found.group(1))
        index = end
    while index < len(clean) and clean[index] in " \t\r\n":
        index += 1
    ports: list[Port] = []
    if index < len(clean) and clean[index] == "(":
        end = balanced(clean, index)
        ports = parse_ports(clean[index + 1:end - 1])
        index = end
    body_start = clean.find(";", index) + 1
    body_end = clean.find("endmodule", body_start)
    body = clean[body_start:body_end]
    offset = clean[:body_start].count("\n") + 1
    module = Module(name=name, path=path, line=line, lines=len(text.splitlines()),
                    summary=comment, ports=ports, parameters=parameters)
    line_at = line_of(body)
    for macro in REGISTER_MACROS:
        for match in re.finditer(rf"`{macro}\b(?!_)", body):
            at = offset + line_at(match.start()) - 1
            if active[at - 1]:
                module.registers += 1
                module.register_macros[macro] = module.register_macros.get(macro, 0) + 1
            else:
                module.simulation_registers += 1
    module.raw_processes = len(re.findall(r"\balways(_ff|_latch)?\s*@", body))
    return module


def body_of(name: str, clean: str) -> tuple[str, int]:
    """The module body and the line its first character sits on."""
    header = re.search(rf"^[ \t]*module\s+{re.escape(name)}\b", clean, re.M)
    start = clean.find(";", header.end())
    while start >= 0 and clean[:start].count("(") != clean[:start].count(")"):
        start = clean.find(";", start + 1)
    start += 1
    end = clean.find("endmodule", start)
    return clean[start:end], clean[:start].count("\n") + 1


def collect(root: Path, paths: list[str]) -> tuple[dict[str, Module], dict[str, tuple[str, list[bool]]]]:
    """Parse each source once; return the modules and their cleaned text."""
    modules: dict[str, Module] = {}
    parsed: dict[str, tuple[str, list[bool]]] = {}
    for path in paths:
        text = (root / path).read_text(encoding="utf-8")
        module = parse_module(path, text)
        if module is None:
            continue
        if module.name in modules:
            raise ValueError(f"Duplicate module {module.name}: {path} and {modules[module.name].path}")
        modules[module.name] = module
        parsed[module.name] = (blanked(text), synthesis_view(text))
    return modules, parsed


def resolve_instances(modules: dict[str, Module], parsed, names, known: set[str]) -> None:
    for name in names:
        clean, active = parsed[name]
        body, offset = body_of(name, clean)
        modules[name].instances, modules[name].vendor = parse_instances(body, offset, active, known)


def index(root: Path = ROOT, prefix: str = RTL) -> dict[str, Module]:
    """Every module declared under the prefix, keyed by module name."""
    modules, parsed = collect(root, tracked(root, prefix))
    resolve_instances(modules, parsed, list(modules), set(modules))
    return modules


# --- Board sources ---------------------------------------------------------
# src/rtl/ holds no top. These three DE10-Lite sources close the composition:
# the composed board proof, its clocking wrapper, and the variant top that
# swaps in the physical-control producer. Naming them here rather than globbing
# src/fpga/ keeps the per-subsystem placement proofs out of the diagram.
BOARD_SOURCES = (
    "src/fpga/de10_lite/v05_proof.sv",
    "src/fpga/de10_lite/n2m_clocking.sv",
    "src/fpga/de10_lite/n2m_controls_system.sv",
)

# The drawn root, and the order the remaining roots follow it.
BOARD_TOP = "v05_proof"

# The owning specification of each source directory. A module's own name is not
# always written in its subsystem's MAS; the directory's contract is.
SPECS = {
    "src/rtl/audio": "wiki/src/rtl/audio/MAS_audio.md",
    "src/rtl/cartridge": "wiki/src/rtl/cartridge/MAS_loader_profile.md",
    "src/rtl/clocking": "wiki/src/rtl/clocking/MAS_clocking.md",
    "src/rtl/common": "wiki/src/rtl/common/MAS_memory_primitives.md",
    "src/rtl/cpu": "wiki/src/rtl/cpu/MAS_cpu.md",
    "src/rtl/display": "wiki/src/rtl/display/MAS_display.md",
    "src/rtl/dma": "wiki/src/rtl/dma/MAS_dma.md",
    "src/rtl/input": "wiki/src/rtl/input/MAS_input.md",
    "src/rtl/interfaces": "wiki/src/rtl/interfaces/MAS_interfaces.md",
    "src/rtl/interrupts": "wiki/src/rtl/interrupts/MAS_interrupts.md",
    "src/rtl/joypad": "wiki/src/rtl/joypad/MAS_joypad.md",
    "src/rtl/memory": "wiki/src/rtl/memory/MAS_memory.md",
    "src/rtl/ppu": "wiki/src/rtl/ppu/MAS_ppu.md",
    "src/rtl/serial": "wiki/src/rtl/serial/MAS_serial.md",
    "src/rtl/snapshot": "wiki/src/rtl/snapshot/MAS_snapshot.md",
    "src/rtl/storage": "wiki/src/rtl/storage/MAS_flash_library.md",
    "src/rtl/system": "wiki/src/rtl/system/MAS_system.md",
    "src/rtl/timer": "wiki/src/rtl/timer/MAS_timer.md",
    "src/rtl/uart": "wiki/src/rtl/uart/MAS_uart.md",
    "src/rtl/vga": "wiki/src/rtl/vga/MAS_vga.md",
    "src/fpga/de10_lite": "wiki/src/board-bring-up.md",
}

# Modules whose owning contract is not their directory's default.
SPEC_OVERRIDES = {
    "n2m_mbc1": "wiki/src/rtl/cartridge/MAS_mbc1_profile.md",
    "n2m_sdram_ctrl": "wiki/src/rtl/storage/MAS_sdram.md",
    "n2m_sim_sdram": "wiki/src/rtl/storage/MAS_sdram.md",
    "n2m_clocking": "wiki/src/rtl/clocking/MAS_clocking.md",
}


def specification(module: Module) -> str:
    directory = module.path.rsplit("/", 1)[0]
    return SPEC_OVERRIDES.get(module.name) or SPECS[directory]


def composition(root: Path = ROOT) -> dict[str, Module]:
    """Every module under src/rtl/ plus the named DE10-Lite board sources."""
    modules, parsed = collect(root, list(tracked(root, RTL)) + list(BOARD_SOURCES))
    if len(modules) != len(parsed):
        raise ValueError("A module name is declared twice")
    resolve_instances(modules, parsed, list(modules), set(modules))
    for path in BOARD_SOURCES:
        if not any(module.path == path for module in modules.values()):
            raise ValueError(f"Board source declared no module: {path}")
    return modules


def packages(root: Path = ROOT) -> list[tuple[str, str, int, str]]:
    """(name, path, lines, summary) for every package under src/rtl/."""
    found = []
    for path in tracked(root, RTL):
        text = (root / path).read_text(encoding="utf-8")
        clean = blanked(text)
        header = re.search(rf"^[ \t]*package\s+({IDENT})", clean, re.M)
        if not header:
            continue
        line = clean[:header.start()].count("\n") + 1
        comment = []
        for previous in reversed(text.splitlines()[:line - 1]):
            stripped = previous.strip()
            if not stripped.startswith("//"):
                break
            comment.insert(0, stripped[2:].strip())
        found.append((header.group(1), path, len(text.splitlines()), " ".join(comment)))
    return found


# --- Drawing ---------------------------------------------------------------
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


def build(modules: dict[str, Module], name: str, instance: str, drawn: set[str]) -> Tile:
    """The tile for one instance, with a child tile for every instance inside it.

    A module already expanded in an earlier diagram is drawn once more as a
    collapsed reference rather than repeated, so the same subtree is not drawn
    twice; inside one diagram every instance is expanded.
    """
    module = modules[name]
    own = own_weight(module)
    inside = [i for i in module.instances if i.view in ("both", "synthesis")]
    if not inside:
        return Tile(name, instance, "module", own)
    if name in drawn:
        return Tile(name, instance, "reference", own)
    drawn.add(name)
    children = [Tile(name, instance, "own", own)]
    children += [build(modules, i.module, i.name, drawn) for i in inside]
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


def stub(module: Module) -> bool:
    """A present-but-unimplemented owner, as its own source comment declares it."""
    return module.summary.lower().startswith("present-but-unimplemented")


def simulation_model(name: str) -> bool:
    """An n2m_sim_* stand-in for a vendor primitive: never synthesized."""
    return name.startswith("n2m_sim_")


def classes(tile: Tile, module: Module) -> str:
    names = ["t-" + {"module": "module", "own": "own", "reference": "ref"}[tile.kind]]
    if stub(module):
        names.append("t-stub")
    if simulation_model(module.name):
        names.append("t-sim")
    return " ".join(names)


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


def svg_tile(tile: Tile, rect, depth: int, module: Module) -> str:
    x, y, width, height = rect
    target = html_escape("#m-" + module.name)
    title = f"{tile.instance}: {module.name} — {counts(module)}"
    parts = [f'<a href="{target}" class="{classes(tile, module)}" data-module="{module.name}">',
             f'<title>{html_escape(title)}</title>',
             f'<rect x="{round(x, 1)}" y="{round(y, 1)}" width="{round(width, 1)}" '
             f'height="{round(height, 1)}" rx="4" />']
    rows = label(tile, module)
    if tile.children:
        head = f"{tile.instance} : {module.name}" if tile.instance != module.name else module.name
        head = f"{head} · {module.lines} L · {module.registers} R"
        head = shortest(head, width) or shortest(module.name, width)
        if head:
            parts.append(f'<text class="h" x="{round(x + 7, 1)}" y="{round(y + 13.5, 1)}">'
                         f'{html_escape(head)}</text>')
    else:
        shown = [(kind, shortest(text, width)) for kind, text in rows]
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
    body = "".join(svg_tile(tile, rect, depth, modules[tile.module]) for tile, rect, depth in placed)
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

    drawn: set[str] = set()
    board = build(modules, BOARD_TOP, BOARD_TOP, drawn)
    composed, shown = diagram([board], modules, 1100,
                              "The DE10-Lite composition: every module instance drawn inside "
                              "the module that instantiates it, sized by measured lines and registers")
    rest = [name for name in modules if name not in shown]
    roots = [name for name in rest if not any(
        parent in rest and view in ("both", "synthesis")
        for parent, _, view in parents.get(name, []))]
    others = [build(modules, name, name, drawn) for name in roots]
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
        'loosely.</p>'
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
        f'<p class="diagram-caption">{len(shown)} modules, drawn at every instance. Two Quartus-'
        'generated PLLs and three Intel primitives are named on their parent blocks but not '
        'drawn: they are not in this repository, so there is nothing here to measure.</p>'
        + panels(modules, shown, parents))

    remainder = (
        '<p class="lead">These modules are under <code>src/rtl/</code> but the composed board '
        'design does not instantiate them. <code>n2m_controls_system</code> is the variant top '
        'that swaps in the physical-control producer; the <code>n2m_sim_*</code> models stand in '
        'for vendor primitives under simulation only.</p>'
        '<div class="diagram-scroll" data-scroll-region tabindex="0" role="region" '
        'aria-label="Modules outside the composed design; scroll horizontally on a narrow screen">'
        + outside + '</div>'
        '<p class="diagram-caption">Drawn at the same scale as the composition above.</p>'
        + panels(modules, also, parents)
        + '<h3>Packages are not blocks</h3>'
        f'<p>{numbers["packages"]} of the {numbers["files"]} files under <code>src/rtl/</code> are '
        'packages. A package declares shared types and constants and is imported, never '
        'instantiated, so it has no place in an instance tree and none is drawn. They are listed '
        'here with their sizes instead.</p>'
        + '<ul class="packages">' + "".join(
            f'<li><a href="{html_escape(relative(path))}" data-source="{html_escape(path)}" '
            f'data-line="1"><code>{html_escape(name)}</code></a> · {count} lines'
            + (f' · {html_escape(text)}' if text else "") + "</li>"
            for name, path, count, text in packages(root)) + "</ul>")

    limits = (
        '<p class="lead">Two boards are supported. The DE10-Lite (MAX 10 '
        '<code>10M50DAF484C7G</code>) is the qualified board: the tree above is rooted at its '
        'composed top and its bring-up is recorded. DE10-Nano (Cyclone V SE '
        '<code>5CSEBA6U23I7</code>) support is in progress; no DE10-Nano top exists in the tree '
        'yet, so none is drawn here.</p>'
        '<div class="comparison">'
        '<div><strong>Generated, not written</strong><p><code>tools/wiki/rtl_modules.py</code> '
        'parses the sources and writes this page. A host test rebuilds it and fails when the '
        'committed page differs, so the diagram cannot drift away from the RTL.</p></div>'
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
    target = root / PAGE
    target.write_text(document(root), encoding="utf-8")
    return target
