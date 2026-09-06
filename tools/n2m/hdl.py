"""Bounded repository-root literal HDL includes, shared by all build paths."""
import re


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
                      lambda m: m[0] if m[0].startswith('"') else ' ',
                      path.read_text(encoding="utf-8"))
        if synthesis and re.search(r'\$(?:readmemh|readmemb|fopen)\b', text):
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
