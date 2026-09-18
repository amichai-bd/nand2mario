#!/usr/bin/env python3
"""Measure the modules under src/rtl/ and the DE10-Lite board sources.

Every number the explorer shows is read from the SystemVerilog sources here:
file line counts, register-macro invocations, ports and instances. Nothing is
estimated, and no synthesis or fit report is consulted, because the repository
retains none and a whole-design fit cannot be attributed to one module.
tools/wiki/rtl_explorer.py draws them; this file only measures.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
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
    view: str          # "both", "synthesis" or "simulation"
    copies: int = 1    # elaborated copies of this one source site
    exact: bool = True # False when a bound is not a literal, so copies is a floor
    label: str = ""    # the generate block this site sits in, when it has one


@dataclass
class Module:
    name: str
    path: str
    line: int          # the line the module keyword is on
    lines: int         # physical lines in the file
    summary: str       # the authored comment block above the module keyword
    ports: list[Port] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    registers: int = 0                 # macro invocations after replication
    register_sites: int = 0            # macro invocations written in the source
    registers_exact: bool = True       # False when a generate bound is not a literal
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
            end = min(end + 1, length)
            out.append("".join(c if c == "\n" else " " for c in text[index - 1:end]))
            index = end
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


def line_of(text: str) -> Callable[[int], int]:
    """A function from an index in `text` to its 1-based line number."""
    breaks = [match.start() for match in re.finditer("\n", text)]
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


# --- Generate replication ---------------------------------------------------
# A `generate for` loop writes one source site and elaborates several copies of
# it. Counting the site once would draw a three-bank frame store as one bank and
# report a ten-slot register file as three flops, so a loop with literal bounds
# is expanded. A bound that is a parameter or an expression is not guessed: the
# site counts once and the module is marked inexact, so its panel can say that
# its counts are a floor rather than a measurement.
LOOP_HEADER = re.compile(
    rf"(?:genvar\s+)?({IDENT})\s*=\s*(\d+)\s*;\s*\1\s*(<=?)\s*(\d+)\s*;\s*"
    rf"\1\s*(?:\+\+|=\s*\1\s*\+\s*(\d+))\s*$")


@dataclass
class Loop:
    start: int              # first index of the loop body inside the module body
    end: int                # one past its last index
    copies: int             # elaborated copies, or 1 when the bound is not literal
    exact: bool             # False when the bound is not literal
    label: str              # the generate block's name, when it has one


def trip_count(header: str) -> int | None:
    """Elaborated copies of a `for` header, or None when a bound is not literal."""
    found = LOOP_HEADER.fullmatch(" ".join(header.split()))
    if not found:
        return None
    start, relation, bound = int(found.group(2)), found.group(3), int(found.group(4))
    step = int(found.group(5)) if found.group(5) else 1
    if step <= 0:
        return None
    span = bound - start + (1 if relation == "<=" else 0)
    return max(0, -(-span // step))


def statement_end(text: str, index: int) -> int:
    """One past the `begin`/`end` block or single statement starting at `index`."""
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    if text.startswith("begin", index):
        depth, cursor = 0, index
        for match in re.finditer(r"\b(begin|end)\b", text[index:]):
            depth += 1 if match.group(1) == "begin" else -1
            cursor = index + match.end()
            if depth == 0:
                return cursor
        return len(text)
    depth = 0
    while index < len(text):
        if text[index] in "([{":
            depth += 1
        elif text[index] in ")]}":
            depth -= 1
        elif text[index] == ";" and depth == 0:
            return index + 1
        index += 1
    return len(text)


def generate_regions(body: str) -> list[tuple[int, int]]:
    """Index ranges covered by `generate ... endgenerate`."""
    regions, opens = [], []
    for match in re.finditer(r"\b(generate|endgenerate)\b", body):
        if match.group(1) == "generate":
            opens.append(match.end())
        elif opens:
            regions.append((opens.pop(), match.start()))
    return regions


def generate_loops(body: str) -> list[Loop]:
    """Every generate-for in the module body, with its elaborated copy count.

    A `for` counts as a generate loop when it declares a genvar or sits inside a
    `generate` region. A procedural `for` inside an `always` block or a function
    can hold neither an instance nor a register macro, so it cannot reach here.
    """
    regions = generate_regions(body)
    loops = []
    for match in re.finditer(r"\bfor\s*\(", body):
        opening = match.end() - 1
        closing = balanced(body, opening)
        header = body[opening + 1:closing - 1]
        inside = any(start <= match.start() < end for start, end in regions)
        if not inside and "genvar" not in header:
            continue
        copies = trip_count(header)
        end = statement_end(body, closing)
        named = re.match(r"\s*begin\s*:\s*(" + IDENT + ")", body[closing:])
        loops.append(Loop(closing, end, copies if copies is not None else 1,
                          copies is not None, named.group(1) if named else ""))
    return loops


def replication(index: int, loops: list[Loop]) -> tuple[int, bool, str]:
    """(copies, exact, innermost label) for a site at this index in the body."""
    copies, exact, label = 1, True, ""
    for loop in loops:
        if loop.start <= index < loop.end:
            copies *= loop.copies
            exact = exact and loop.exact
            label = loop.label or label
    return copies, exact, label


def array_copies(text: str) -> tuple[int, bool]:
    """Elaborated copies of an instance array range such as `[3:0]`."""
    found = re.fullmatch(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", " ".join(text.split()))
    if not found:
        return 1, False
    high, low = int(found.group(1)), int(found.group(2))
    return abs(high - low) + 1, True


def parse_instances(body: str, offset: int, active: list[bool], known: set[str]) -> tuple[list[Instance], list[Instance]]:
    """Every `<type> [#(...)] <name> [[...]] (` site, by the line it starts on."""
    repo, vendor = [], []
    line_at = line_of(body)
    loops = generate_loops(body)
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
        array, array_exact = 1, True
        if index < len(body) and body[index] == "[":
            closing = balanced(body, index)
            array, array_exact = array_copies(body[index:closing])
            index = closing
            while index < len(body) and body[index] in " \t\r\n":
                index += 1
        if index >= len(body) or body[index] != "(":
            continue
        line = offset + line_at(match.start()) - 1
        view = "synthesis" if active[line - 1] else "simulation"
        copies, exact, label = replication(match.start(), loops)
        target = repo if head in known else vendor
        target.append(Instance(head, name.group(1), line, view, copies * array,
                               exact and array_exact, label))
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
    declarations = re.findall(rf"^[ \t]*module\s+({IDENT})", clean, re.M)
    if not declarations:
        return None
    if len(declarations) > 1:
        # One module per file is what the explorer indexes, and a second one
        # would be measured nowhere. Refuse rather than drop it silently.
        raise ValueError(f"{path} declares more than one module: {', '.join(declarations)}")
    header = re.search(rf"^[ \t]*module\s+({IDENT})", clean, re.M)
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
        declared = clean[index + 1:end - 1]
        if declared.strip() and not re.search(r"\b(input|output|inout|ref)\b", declared):
            # A non-ANSI header names its ports here and declares their direction
            # and width in the body. Reporting them all as `input logic` would be
            # a wrong answer to a question the page promises to answer.
            raise ValueError(f"{path} uses a non-ANSI port header; the explorer reads direction "
                             "and width from the header, so teach parse_ports that form "
                             "rather than publishing a wrong one")
        ports = parse_ports(declared)
        index = end
    body, offset = body_of(name, clean)
    module = Module(name=name, path=path, line=line, lines=len(text.splitlines()),
                    summary=comment, ports=ports, parameters=parameters)
    line_at = line_of(body)
    loops = generate_loops(body)
    for macro in REGISTER_MACROS:
        for match in re.finditer(rf"`{macro}\b(?!_)", body):
            at = offset + line_at(match.start()) - 1
            copies, exact, _ = replication(match.start(), loops)
            if not active[at - 1]:
                module.simulation_registers += copies
                continue
            module.registers += copies
            module.register_sites += 1
            module.registers_exact = module.registers_exact and exact
            module.register_macros[macro] = module.register_macros.get(macro, 0) + copies
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


def stub(module: Module) -> bool:
    """A present-but-unimplemented owner, as its own source comment declares it."""
    return module.summary.lower().startswith("present-but-unimplemented")


def simulation_model(name: str) -> bool:
    """An n2m_sim_* stand-in for a vendor primitive: never synthesized."""
    return name.startswith("n2m_sim_")


def loop_sites(root: Path = ROOT) -> list[tuple[str, int, int, bool]]:
    """(path, line, copies, exact) for every generate-for under src/rtl/."""
    found = []
    for path in tracked(root, RTL):
        clean = blanked((root / path).read_text(encoding="utf-8"))
        header = re.search(rf"^[ \t]*module\s+({IDENT})", clean, re.M)
        if not header:
            continue
        body, offset = body_of(header.group(1), clean)
        for loop in generate_loops(body):
            found.append((path, offset + body[:loop.start].count("\n"), loop.copies, loop.exact))
    return found


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
        lines = text.splitlines()
        found.append((header.group(1), path, len(lines), summary_comment(lines, line)))
    return found
