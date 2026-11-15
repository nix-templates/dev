"""Python: imports read from the syntax tree, plus a few calls and statements that are side effects.

A Jupyter notebook is read as the Python in its code cells.
"""

import ast
import json
import posixpath
import sys

from .model import Ref, Scan
from .walk import read

STDLIB = frozenset(sys.stdlib_module_names)

# Calls that reach outside the function whatever was imported.
_BUILTIN_EFFECTS = frozenset({"open", "print", "input", "exec", "eval", "breakpoint"})
_ATTRIBUTE_EFFECTS = frozenset(
    {
        ("datetime", "now"),
        ("datetime", "utcnow"),
        ("datetime", "today"),
        ("date", "today"),
        ("uuid", "uuid1"),
        ("uuid", "uuid4"),
    }
)


def is_test(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (
        bool({"tests", "test"} & set(parts[:-1]))
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def _roots(sources: list[str], configured: list[str]) -> list[str]:
    """Directories that hold top-level modules, most specific first."""
    roots = {root.strip("/") for root in configured} | {""}
    packages = {posixpath.dirname(path) for path in sources if posixpath.basename(path) == "__init__.py"}
    for package in packages:
        top = package
        while posixpath.dirname(top) in packages:
            top = posixpath.dirname(top)
        roots.add(posixpath.dirname(top))
    return sorted(roots, key=len, reverse=True)


def _module_name(path: str, root: str) -> str | None:
    if root and not path.startswith(root + "/"):
        return None
    inside = path[len(root) + 1 :] if root else path
    parts = inside[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


def _longest(index: dict[str, str], dotted: str) -> str | None:
    parts = dotted.split(".")
    for length in range(len(parts), 0, -1):
        found = index.get(".".join(parts[:length]))
        if found:
            return found
    return None


def _dotted(node: ast.AST) -> list[str]:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return parts[::-1]
    return []


def _cells(text: str) -> list[tuple[int, str]] | None:
    """The code cells of a notebook as (number, Python); None when its kernel is not Python."""
    data = json.loads(text)
    metadata = data.get("metadata", {})
    language = metadata.get("kernelspec", {}).get("language") or metadata.get("language_info", {}).get("name") or "python"
    if language.lower() != "python":
        return None
    cells = []
    for number, cell in enumerate(data.get("cells", []), start=1):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        source = "".join(source) if isinstance(source, list) else str(source)
        # %magic and !shell lines are IPython, not Python.
        lines = ["" if line.lstrip().startswith(("%", "!", "?")) else line for line in source.splitlines()]
        cells.append((number, "\n".join(lines) + "\n"))
    return cells


_IMPORT_CALLS = frozenset({"import_module", "__import__", "run_module"})


def _loaded_file(path: str, call: ast.Call, known: frozenset[str]) -> str | None:
    """The .py file a spec_from_file_location call names: beside the caller, or the only one of that name."""
    for node in ast.walk(call):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".py"):
            beside = posixpath.normpath(posixpath.join(posixpath.dirname(path), node.value))
            if beside in known:
                return beside
            same = [other for other in known if other == node.value or other.endswith("/" + node.value.lstrip("./"))]
            if len(same) == 1:
                return same[0]
    return None


def _beside(path: str, dotted: str, known: frozenset[str]) -> str | None:
    """A module next to a script.

    A file that is not in a package is run from its own directory, so Python
    finds its neighbours by bare name before anything else.
    """
    directory = posixpath.dirname(path)
    if posixpath.join(directory, "__init__.py") in known:
        return None
    parts = dotted.split(".")
    for length in range(len(parts), 0, -1):
        base = posixpath.join(directory, *parts[:length])
        for candidate in (base + ".py", posixpath.join(base, "__init__.py")):
            if candidate in known:
                return candidate
    return None


def _refs(path: str, tree: ast.AST, package: str, index: dict[str, str], cell: int, known: frozenset[str]) -> list[Ref]:
    """What one syntax tree uses. In a notebook the cell's number stands in for the line."""
    refs: list[Ref] = []

    def at(node: ast.AST) -> int:
        return cell or node.lineno

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.append(_ref(path, at(node), alias.name, index, known))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parent = package.split(".") if package else []
                parent = parent[: len(parent) - (node.level - 1)] if node.level > 1 else parent
                base = ".".join(parent + ([base] if base else []))
            for alias in node.names:
                wanted = f"{base}.{alias.name}" if base and alias.name != "*" else base or alias.name
                refs.append(_ref(path, at(node), wanted, index, None if node.level else known))
        elif isinstance(node, ast.Global):
            refs.append(Ref(path, at(node), "effect", "global", "global " + ", ".join(node.names)))
        elif isinstance(node, ast.Call):
            called = _dotted(node.func)
            first = node.args[0] if node.args else None
            named = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
            if called and called[-1] in _IMPORT_CALLS and named:
                # importlib.import_module("a.b") with the name written out is an import like any other.
                refs.append(_ref(path, at(node), named, index, known))
            elif called and called[-1] == "spec_from_file_location":
                # A module loaded by the path of its file: the file's name is in the call.
                target = _loaded_file(path, node, known)
                if target:
                    refs.append(Ref(path, at(node), "internal", target, posixpath.basename(target)))
                elif named:
                    refs.append(_ref(path, at(node), named, index, known))
            if len(called) == 1 and called[0] in _BUILTIN_EFFECTS:
                refs.append(Ref(path, at(node), "effect", called[0] + "()", called[0] + "()"))
            elif len(called) >= 2 and tuple(called[-2:]) in _ATTRIBUTE_EFFECTS:
                name = ".".join(called[-2:]) + "()"
                refs.append(Ref(path, at(node), "effect", name, ".".join(called) + "()"))
    return refs


def extract(
    root: str,
    files: list[str],
    configured_roots: list[str],
    include_tests: bool,
    scan: Scan,
    scripts: list[str] | None = None,
) -> None:
    """scripts are files with no extension whose first line names Python."""
    sources = [path for path in files if path.endswith(".py")]
    roots = _roots(sources, configured_roots)
    index: dict[str, str] = {}
    name_of: dict[str, tuple[str, bool]] = {}
    for path in sources:
        for source_root in roots:
            name = _module_name(path, source_root)
            if name is None:
                continue
            index.setdefault(name, path)
            name_of.setdefault(path, (name, posixpath.basename(path) == "__init__.py"))

    refs: list[Ref] = []
    known = frozenset(sources)
    for path in scripts or []:
        scan.language[path] = "python"
    for path in sources + sorted(scripts or []) + [path for path in files if path.endswith(".ipynb")]:
        if not include_tests and is_test(path):
            scan.tests.add(path)
            continue
        text = read(root, path)
        cells: list[tuple[int, str]] | None = [(0, text)]
        if path.endswith(".ipynb"):
            try:
                cells = _cells(text)
            except (ValueError, AttributeError, TypeError) as error:
                scan.files.append(path)
                scan.unreadable.append((path, f"not a notebook: {error}"))
                continue
            if cells is None:
                continue
        scan.files.append(path)
        module, is_package = name_of.get(path, ("", False))
        package = module if is_package else module.rpartition(".")[0]
        for cell, code in cells:
            try:
                tree = ast.parse(code, filename=path)
            except (SyntaxError, ValueError) as error:
                scan.unreadable.append((path, f"cell {cell}: {error}" if cell else str(error)))
                break
            refs.extend(_refs(path, tree, package, index, cell, known))
    scan.refs.extend(ref for ref in refs if ref.target != ref.file)


def _ref(path: str, line: int, dotted: str, index: dict[str, str], known: frozenset[str] | None) -> Ref:
    target = (_beside(path, dotted, known) if known else None) or _longest(index, dotted)
    if target:
        return Ref(path, line, "internal", target, dotted)
    return Ref(path, line, "external", dotted.split(".")[0], dotted)
