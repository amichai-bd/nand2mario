"""Bounded repository-root literal HDL includes, shared by all build paths."""
import re


def synthesis_text(text):
    """Remove branches proven inactive with the tool-owned SYNTHESIS macro.

    Unknown conditions retain both alternatives. Include discovery still reads
    every branch, so this view only governs rejection of external file I/O.
    """
    if re.search(r"`(?:define|undef)\s+SYNTHESIS\b|`undefineall\b", text):
        raise ValueError("FPGA sources must not redefine SYNTHESIS")
    stack = []
    enabled = True
    result = []
    continued = False
    for line in text.splitlines():
        # A continued macro body is not a source-level conditional branch.
        # Reject guard tokens in continuation contexts rather than expanding
        # macros or accidentally hiding active file reads after the definition.
        continuation = continued or re.match(r"\s*`define\b", line)
        continued = line.rstrip().endswith("\\")
        if continuation:
            if re.search(r"`(?:ifdef|ifndef|elsif|else|endif)\b", line):
                raise ValueError("unsupported FPGA conditional in macro continuation")
            if enabled:
                result.append(line)
            continue
        match = re.fullmatch(r"\s*`(ifdef|ifndef|elsif)\s+([A-Za-z_][A-Za-z0-9_]*)\s*", line)
        end = re.fullmatch(r"\s*`(else|endif)\s*", line)
        if match:
            directive, name = match.groups()
            condition = (directive != "ifndef") if name == "SYNTHESIS" else None
            if directive != "elsif":
                stack.append([enabled, True, False])
            elif not stack or stack[-1][2]:
                raise ValueError("unmatched FPGA conditional branch")
            parent, remaining, _ = stack[-1]
            enabled = parent and remaining and condition is not False
            stack[-1][1] = remaining and condition is not True
        elif end:
            if not stack:
                raise ValueError("unmatched FPGA conditional branch")
            if end[1] == "endif":
                enabled = stack.pop()[0]
            else:
                parent, remaining, seen_else = stack[-1]
                if seen_else:
                    raise ValueError("duplicate FPGA else branch")
                enabled = parent and remaining
                stack[-1][1:] = [False, True]
        elif re.search(r"`(?:ifdef|ifndef|elsif|else|endif)\b", line):
            raise ValueError("unsupported FPGA conditional syntax")
        elif enabled:
            result.append(line)
    if stack:
        raise ValueError("unterminated FPGA conditional branch")
    return "\n".join(result)


def dependencies(root, sources, *, synthesis=False):
    root = root.resolve()
    found = []
    active = set()

    def visit(name):
        path = root / name
        if (not re.fullmatch(r"src/[A-Za-z0-9_./-]+\.(?:sv|svh)", name)
                or any(part in ("", ".", "..") for part in name.split("/"))
                or path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(root)):
            raise ValueError(f"missing or unsupported HDL dependency: {name}")
        if name in active:
            raise ValueError(f"cyclic HDL include: {name}")
        if name in found:
            return
        if len(found) >= 256:
            raise ValueError("HDL dependency limit exceeded")
        found.append(name)
        active.add(name)
        # Preserve quoted strings while removing comments; commented includes
        # are not dependencies, but all conditional branches are conservatively read.
        text = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
                      lambda m: m[0] if m[0].startswith('"') else ' ' + '\n' * m[0].count('\n'),
                      path.read_text(encoding="utf-8"))
        if synthesis and re.search(r'\$(?:readmemh|readmemb|fopen)\b', synthesis_text(text)):
            raise ValueError(f"external FPGA source dependencies are unsupported: {name}")
        for match in re.finditer(r'`include\b([^\n]*)', text):
            literal = re.fullmatch(r'\s*"(src/[A-Za-z0-9_./-]+\.(?:sv|svh))"\s*', match[1])
            if not literal:
                raise ValueError(f"unsupported HDL include in {name}: use a literal src/ path")
            include = literal[1]
            # Tools may search beside the including file before their -I path.
            if (path.parent / include).exists():
                raise ValueError(f"ambiguous HDL include in {name}: {include}")
            visit(include)
        active.remove(name)

    for source in sources:
        visit(source)
    return found
