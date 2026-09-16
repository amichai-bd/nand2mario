"""Static input closure of a standalone host unit; a positive subset, not a Python analyzer.

A host unit is one `test_*.py` file that `catalogue.run_unit` executes with
`python -m unittest discover -s DIR -t DIR` from the repository root with
`tools/` on PYTHONPATH. Its module imports are derived here by following every
import statement transitively across the repository in that search order,
after evaluating the module's own `sys.path` edits. Data it reads cannot be
derived, so the catalogue entry declares them in `inputs`; that declaration is
the author's assertion that the closure is complete, and `check` guards it
against drift: every path anchored at the test module's own location must be
declared or derived, and a declared module must not already be derived.

An import no search directory serves is resolved against every module of that
name in the tree, so a branch another entry point's `sys.path` makes reachable
still contributes its inputs; the closure over-approximates and never omits.
A `sys.path` edit that cannot be evaluated could shadow any later import, so
it widens every absolute import in the closure to all same-named modules in
the tree as well. A name found nowhere in the tree must be a standard-library
module or a package the catalogue names in `external_imports`.
"""
import ast
from pathlib import Path
import sys

from .python_tb import _resolve

# The search order catalogue.run_unit gives a unit beyond its own sys.path edits.
RUNTIME_DIRS = ("", "tools")
# Generated output and other checkouts are never a unit's input.
IGNORED = ("workdir", "worktrees", ".git", ".venv", "__pycache__", "node_modules")
PATH_METHODS = ("resolve", "absolute")


class Unknown(ValueError):
    """The unit declares no inputs, so its data closure is unknown."""


class Module:
    """One parsed module with its evaluable `Path(__file__)`-anchored names."""

    def __init__(self, root, path):
        self.root = root
        self.path = path
        self.tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        self.names, self.sys_path, self.imports = {}, [], []
        # One pass: bound names, import statements and the statements that edit sys.path.
        pending = [(self.tree, None)]
        while pending:
            node, statement = pending.pop()
            if isinstance(node, ast.stmt):
                statement = node
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                # A name bound twice is ambiguous and stays unevaluable.
                self.names[name] = None if name in self.names else node.value
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self.imports.append(node)
            elif (isinstance(node, ast.Attribute) and node.attr == "path" and isinstance(node.value, ast.Name)
                    and node.value.id == "sys" and statement not in self.sys_path):
                self.sys_path.append(statement)
            pending.extend((child, statement) for child in ast.iter_child_nodes(node))
        self.imports.reverse()
        self.resolved = {}
        self.dirs = self.references = None
        # Set by _search_dirs when an edit names a directory only the caller knows.
        self.ambiguous = False

    def search_dirs(self):
        if self.dirs is None:
            self.dirs = self._search_dirs()
        return self.dirs

    def anchored_paths(self):
        if self.references is None:
            self.references = self._anchored_paths()
        return self.references

    def resolve(self, dirs):
        """Import groups under one search order; cached because units share most closures."""
        key = tuple(dirs)
        if key not in self.resolved:
            self.resolved[key] = [_resolve(node, self.path, dirs) for node in self.imports]
        return self.resolved[key]

    def evaluate(self, node, seen=()):
        """The filesystem path a `Path(__file__)`-anchored expression names, or None."""
        if isinstance(node, ast.Name):
            if node.id == "__file__":
                return self.path
            value = self.names.get(node.id)
            return None if value is None or node.id in seen else self.evaluate(value, (*seen, node.id))
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in ("Path", "str") and len(node.args) == 1 and not node.keywords:
                return self.evaluate(node.args[0], seen)
            if isinstance(func, ast.Attribute) and func.attr in PATH_METHODS and not node.args:
                return self.evaluate(func.value, seen)
            if (isinstance(func, ast.Attribute) and func.attr == "with_name" and len(node.args) == 1
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                base = self.evaluate(func.value, seen)
                return None if base is None else base.with_name(node.args[0].value)
            return None
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            base = self.evaluate(node.value, seen)
            return None if base is None else base.parent
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents"
                and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int)):
            base = self.evaluate(node.value.value, seen)
            return None if base is None else base.parents[node.slice.value]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            base = self.evaluate(node.left, seen)
            if base is not None and isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
                return base / node.right.value
            return None
        return None

    def _search_dirs(self):
        """Directories this module's own sys.path edits put in front of the search."""
        dirs = []
        for statement in self.sys_path:
            for node in ast.walk(statement):
                added = []
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("insert", "append", "extend")
                        and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "path"):
                    added = node.args[-1:] if node.func.attr != "extend" else node.args
                    if node.func.attr == "extend":
                        added = [e for a in added if isinstance(a, (ast.List, ast.Tuple)) for e in a.elts] or [None]
                elif (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript)
                        and isinstance(node.targets[0].value, ast.Attribute) and node.targets[0].value.attr == "path"):
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        added = node.value.elts
                    elif not isinstance(node.value, ast.Name):
                        added = [None]
                    # `sys.path[:] = prior` restores an earlier copy and adds nothing.
                for expression in added:
                    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
                        path = self.root / expression.value
                    else:
                        path = None if expression is None else self.evaluate(expression)
                    if path is None and expression is not None:
                        # `root / 'tools'` on a caller-supplied root: the constant names the
                        # repository directory, as python_tb's fixture builders rely on.
                        constants = [n.value for n in ast.walk(expression)
                                     if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                        if len(constants) == 1 and (self.root / constants[0]).is_dir():
                            path = self.root / constants[0]
                    if path is None:
                        self.ambiguous = True
                    elif path.resolve().is_dir():
                        dirs.append(path.resolve())
        return dirs

    def _anchored_paths(self):
        """Repository paths the module names relative to its own location, outside sys.path edits.

        A name bound to a directory is a definition, not a reference; its uses
        through `/`, `.glob()` or another attribute are the references. A bare
        name passed on as a value is not seen; that is the declaration's job.
        """
        skip = {id(n) for s in self.sys_path for n in ast.walk(s)}
        found = set()
        pending = [self.tree]
        while pending:
            node = pending.pop()
            if id(node) in skip:
                continue
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                path = self.evaluate(node.value)
                if path is not None and path.is_dir():
                    continue
            if isinstance(node, ast.Attribute) and node.attr != "parent":
                path = self.evaluate(node.value)
                if path is not None:
                    found.add(path.resolve())
                    continue
            if isinstance(node, ast.expr) and not isinstance(node, (ast.Name, ast.Constant)):
                path = self.evaluate(node)
                if path is not None:
                    found.add(path.resolve())
                    continue
            pending.extend(ast.iter_child_nodes(node))
        return found


def relative(root, path):
    """Repository-relative posix path, or None when the path is outside or ignored."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        try:
            parts = path.resolve().relative_to(root).parts
        except ValueError:
            return None
    if not parts or parts[0] in IGNORED:
        return None
    return "/".join(parts)


def index(root, cache):
    """Every module and package in the tree by name: the fallback for an import no search directory serves."""
    if "index" not in cache:
        found = {}
        for path in Path(root).rglob("*.py"):
            if relative(root, path):
                name = path.parent.name if path.name == "__init__.py" else path.stem
                found.setdefault(name, []).append(path.resolve())
        cache["index"] = found
    return cache["index"]


def everywhere(root, cache, node):
    """Every tree module one absolute import statement could load from an unknown search directory."""
    found = []
    if isinstance(node, ast.Import):
        requests = [(alias.name.split("."), []) for alias in node.names]
    elif node.level:
        return found
    else:
        requests = [((node.module or "").split("."), [alias.name for alias in node.names])]
    for parts, names in requests:
        for candidate in index(root, cache).get(parts[0], []):
            found.append(candidate)
            package = candidate.parent if candidate.name == "__init__.py" else None
            for member in (*parts[1:], *names):
                if package is None:
                    break
                for option in (package / (member + ".py"), package / member / "__init__.py"):
                    if option.is_file():
                        found.append(option.resolve())
                        break
                package = package / member if (package / member).is_dir() else None
    return found


def derive(root, start, externals, cache, extra=()):
    """(modules, references): the transitive import closure of a unit and the paths it anchors.

    Every import statement counts, including ones inside functions and
    branches. An import that resolves to no repository module must be a
    standard-library module or a declared external package.
    """
    root = Path(root).resolve()
    start = Path(start).resolve()
    seen, shared, todo = {}, [], [start, *(root / p for p in extra)]
    references = set()
    ambiguous = False
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen[path] = True
        module = cache.get(path)
        if module is None:
            module = cache[path] = Module(root, path)
        local = module.search_dirs()
        if module.ambiguous and not ambiguous:
            # Restart so every import already followed is widened too.
            ambiguous = True
            seen, shared, todo = {}, [], [start, *(root / p for p in extra)]
            continue
        shared += [d for d in local if d not in shared]
        # Only sys.path serves absolute imports: the unit's own directory (unittest discover
        # -t) and the runtime directories, never an imported helper's own directory.
        dirs = local + [d for d in shared if d not in local] + [start.parent]
        dirs += [d for d in (root / s for s in RUNTIME_DIRS) if d not in dirs]
        for node, groups in zip(module.imports, module.resolve(dirs)):
            if ambiguous:
                todo += everywhere(root, cache, node)
            if not groups:
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                else:
                    names = [(node.module or "").split(".")[0]] if not node.level else [""]
                for name in names:
                    if name in sys.stdlib_module_names or name in externals:
                        continue
                    elsewhere = index(root, cache).get(name) if name else None
                    if not elsewhere:
                        raise ValueError(f"undeclared import {name or '.'} at line {node.lineno} of "
                                         f"{relative(root, path)}")
                    todo += elsewhere
                continue
            for group in groups:
                todo += [p for p in group if relative(root, p)]
        if path == start:
            references = {relative(root, p) for p in module.anchored_paths() if relative(root, p)}
    return {relative(root, p) for p in seen}, references


def check(root, path, entry, externals, cache):
    """The problems one catalogue unit's closure has; empty when it is derivable and declared consistently."""
    root = Path(root).resolve()
    declared = entry.get("inputs")
    try:
        modules, references = derive(root, root / path, externals, cache)
    except Unknown as error:
        return [f"unit {path} closure is unknown: {error}"] if declared is not None else []
    except (ValueError, SyntaxError) as error:
        return [f"unit {path}: {error}"]
    if declared is None:
        return []
    problems = []
    loaded = []
    for input_path in declared:
        target = root / input_path
        if relative(root, target) != input_path or not target.exists():
            problems.append(f"unit {path} declares a missing or out-of-tree input: {input_path}")
        elif input_path in modules:
            problems.append(f"unit {path} declares an input its imports already reach: {input_path}")
        elif input_path.endswith(".py"):
            loaded.append(input_path)
    if loaded:
        try:
            modules = derive(root, root / path, externals, cache, extra=loaded)[0]
        except (Unknown, ValueError, SyntaxError) as error:
            return problems + [f"unit {path}: {error}"]
    covered = modules | set(declared)
    directories = tuple(d + "/" for d in declared if (root / d).is_dir())
    for reference in sorted(references):
        if reference in covered or reference.startswith(directories):
            continue
        if (root / reference).is_dir() and any(d.startswith(reference + "/") for d in declared):
            # A declared child narrows a reference to a wider directory; the author owns that choice.
            continue
        problems.append(f"unit {path} references an undeclared input: {reference}"
                        + ("/" if (root / reference).is_dir() else ""))
    return problems


def closure(root, path, entry, externals, cache, files):
    """Every repository file a declared unit depends on; `files(dir)` lists a directory's tracked files."""
    if entry.get("inputs") is None:
        raise Unknown("no declared inputs")
    root = Path(root).resolve()
    modules, _ = derive(root, root / path, externals, cache,
                        extra=[p for p in entry["inputs"] if p.endswith(".py") and (root / p).is_file()])
    paths = set(modules)
    for input_path in entry["inputs"]:
        if (root / input_path).is_dir():
            paths.update(files(input_path))
        else:
            paths.add(input_path)
    return paths
