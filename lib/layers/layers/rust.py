"""Rust: crate dependencies from Cargo.toml, module references from paths in the source.

Crate-level edges are exact: they come from the manifests. Module-level edges
are read from `use` declarations and qualified paths in the text, with modules
located by the standard file layout (src/a/b.rs or src/a/b/mod.rs is
crate::a::b). `#[path]` attributes and names brought in by glob imports or
macros are not followed.
"""

import bisect
import posixpath
import re
import tomllib
from dataclasses import dataclass, field

from .model import Ref, Scan
from .walk import read

STD = frozenset({"std", "core", "alloc", "proc_macro", "test"})

_RAW_STRING = re.compile(r'(?:b|c)?r(#*)"')


def strip(src: str) -> str:
    """Blank out comments, string contents and char literals; offsets and newlines stay."""
    out = list(src)
    n = len(src)

    def blank(start: int, end: int) -> None:
        for k in range(start, min(end, n)):
            if out[k] != "\n":
                out[k] = " "

    i = 0
    while i < n:
        c = src[i]
        if c == "/" and src.startswith("//", i):
            end = src.find("\n", i)
            end = n if end < 0 else end
            blank(i, end)
            i = end
        elif c == "/" and src.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif src.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            blank(i, j)
            i = j
        elif c in "rbc" and not (i and (src[i - 1].isalnum() or src[i - 1] == "_")) and (raw := _RAW_STRING.match(src, i)):
            closing = '"' + raw.group(1)
            end = src.find(closing, raw.end())
            end = n if end < 0 else end
            blank(raw.end(), end)
            i = end + len(closing)
        elif c == '"':
            j = i + 1
            while j < n and src[j] != '"':
                j += 2 if src[j] == "\\" else 1
            blank(i + 1, j)
            i = j + 1
        elif c == "'":
            if src.startswith("\\", i + 1):
                # An escaped char: '\n', '\\', '\'', '\x41', '\u{1F600}'.
                end = src.find("'", i + 3)
                end = n if end < 0 else end
                blank(i + 1, end)
                i = end + 1
            elif src.startswith("'", i + 2):
                blank(i + 1, i + 2)
                i += 3
            else:
                i += 1  # a lifetime or a loop label
        else:
            i += 1
    return "".join(out)


def _matching_brace(code: str, open_at: int) -> int:
    depth = 0
    for k in range(open_at, len(code)):
        if code[k] == "{":
            depth += 1
        elif code[k] == "}":
            depth -= 1
            if depth == 0:
                return k
    return len(code) - 1


_TEST_MODULE = re.compile(
    r"#\[cfg\((?:test|(?:all|any)\([^\]]*\btest\b[^\]]*\))\)\]\s*"
    r"(?:#\[[^\]]*\]\s*)*(?:pub(?:\s*\([^)]*\))?\s+)?mod\s+\w+\s*\{"
)


def drop_test_modules(code: str) -> str:
    """Blank out `#[cfg(test)] mod name { ... }` blocks in stripped code."""
    position = 0
    while match := _TEST_MODULE.search(code, position):
        end = _matching_brace(code, match.end() - 1) + 1
        blanked = "".join(ch if ch == "\n" else " " for ch in code[match.start() : end])
        code = code[: match.start()] + blanked + code[end:]
        position = end
    return code


def _split_top(text: str) -> list[str]:
    parts, depth, start = [], 0, 0
    for k, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:k])
            start = k + 1
    parts.append(text[start:])
    return parts


def _expand(tree: str) -> list[str]:
    tree = tree.lstrip(":")
    brace = tree.find("{")
    if brace < 0:
        return [tree] if tree else []
    inner = tree[brace + 1 : _matching_brace(tree, brace)]
    return [tree[:brace] + sub for part in _split_top(inner) for sub in _expand(part)]


def expand_use(tree: str) -> list[list[str]]:
    """`a::{b, c::{d, self}}` becomes [[a, b], [a, c, d], [a, c]]."""
    tree = re.sub(r"\s+as\s+\w+", "", tree)
    tree = "".join(tree.split())
    paths = []
    for path in _expand(tree):
        segments = [s for s in path.split("::") if s and s != "*"]
        if len(segments) > 1 and segments[-1] == "self":
            segments.pop()
        if segments:
            paths.append(segments)
    return paths


_USE = re.compile(r"\buse\s+(?=[A-Za-z_:{*])([^;]*);")
_EXTERN = re.compile(r"\bextern\s+crate\s+(\w+)")
_PATH = re.compile(r"(?<![\w:$])((?:[A-Za-z_]\w*)(?:\s*::\s*[A-Za-z_]\w*)+)")

# Side effects that are not a path into another crate.
_EFFECTS = (
    (re.compile(r"\b(println|eprintln|print|eprint|dbg)\s*!"), lambda m: m.group(1) + "!"),
    (re.compile(r"\bstatic\s+mut\b"), lambda m: "static mut"),
    (re.compile(r"\b(Instant|SystemTime|Utc|Local)\s*::\s*now\b"), lambda m: m.group(1) + "::now"),
    # Methods of std::path::Path that look at the disk.
    (
        re.compile(r"\.\s*(exists|try_exists|is_file|is_dir|is_symlink|read_dir|read_link|canonicalize|symlink_metadata)\s*\(\s*\)"),
        lambda m: "Path::" + m.group(1),
    ),
)


@dataclass
class Crate:
    package: str
    name: str  # the name code imports it by
    dir: str  # "" for a crate at the repository root
    manifest: str
    src: str
    modules: dict[tuple[str, ...], str] = field(default_factory=dict)
    deps: dict[str, tuple[str, str]] = field(default_factory=dict)  # import name -> (kind, target)
    declared: list[tuple[str, int]] = field(default_factory=list)  # deps a build pulls in, with line

    def root_file(self) -> str:
        return self.modules.get((), self.manifest)


def _join(directory: str, name: str) -> str:
    return posixpath.normpath(posixpath.join(directory, name)) if directory else posixpath.normpath(name)


def _is_test(crate: Crate, path: str) -> bool:
    inside = path[len(crate.dir) + 1 :] if crate.dir else path
    parts = inside.split("/")
    name = parts[-1]
    return (
        bool({"tests", "benches", "examples"} & set(parts[:-1]))
        or name in {"build.rs", "tests.rs", "test.rs"}
        or name.endswith(("_test.rs", "_tests.rs"))
    )


def _load_manifests(root: str, files: list[str], scan: Scan) -> dict[str, dict]:
    manifests = {}
    for path in files:
        if posixpath.basename(path) != "Cargo.toml":
            continue
        try:
            manifests[path] = tomllib.loads(read(root, path))
        except tomllib.TOMLDecodeError as error:
            scan.unreadable.append((path, str(error)))
    return manifests


def _workspace_deps(manifests: dict[str, dict], crate_dir: str) -> tuple[str, dict]:
    """The [workspace.dependencies] that apply to a crate, with the workspace's directory."""
    directory = crate_dir
    while True:
        data = manifests.get(_join(directory, "Cargo.toml"))
        if data and isinstance(data.get("workspace"), dict):
            return directory, data["workspace"].get("dependencies", {})
        if not directory:
            return "", {}
        directory = posixpath.dirname(directory)


def _dependency(name: str, spec, base: str, workspace: tuple[str, dict]) -> tuple[str, str, str, bool]:
    """The name the manifest gives a dependency, what it is, and whether the manifest renames it."""
    if isinstance(spec, dict) and spec.get("workspace") is True:
        base, spec = workspace[0], workspace[1].get(name, {})
    renamed = isinstance(spec, dict) and "package" in spec
    package = spec["package"] if renamed else name
    path = spec.get("path") if isinstance(spec, dict) else None
    if isinstance(path, str):
        return name.replace("-", "_"), "internal", _join(base, path), renamed
    return name.replace("-", "_"), "external", package.replace("-", "_"), renamed


def _line_of_key(text: str, name: str) -> int:
    pattern = re.compile(rf"^\s*(?:{re.escape(name)}\s*[=.]|\[[\w.'\"() =-]*dependencies\.{re.escape(name)}\])", re.M)
    match = pattern.search(text)
    return text.count("\n", 0, match.start()) + 1 if match else 1


def discover(root: str, files: list[str], scan: Scan) -> list[Crate]:
    manifests = _load_manifests(root, files, scan)
    crates = []
    listed: dict[str, list] = {manifest: [] for manifest in manifests}
    for manifest, data in manifests.items():
        package = data.get("package")
        if not isinstance(package, dict) or not isinstance(package.get("name"), str):
            continue
        directory = posixpath.dirname(manifest)
        lib = data.get("lib", {}) if isinstance(data.get("lib"), dict) else {}
        lib_path = lib.get("path", "src/lib.rs")
        crate = Crate(
            package=package["name"],
            name=lib.get("name", package["name"]).replace("-", "_"),
            dir=directory,
            manifest=manifest,
            src=_join(directory, posixpath.dirname(lib_path)),
        )
        workspace = _workspace_deps(manifests, directory)
        text = read(root, manifest)
        tables = [(data.get("dependencies", {}), True), (data.get("build-dependencies", {}), True)]
        tables.append((data.get("dev-dependencies", {}), False))
        for target in (data.get("target") or {}).values():
            if isinstance(target, dict):
                tables.append((target.get("dependencies", {}), True))
                tables.append((target.get("dev-dependencies", {}), False))
        for table, built in tables:
            for name, spec in (table or {}).items():
                listed[manifest].append((*_dependency(name, spec, directory, workspace), built, _line_of_key(text, name)))
        crates.append(crate)

    by_dir = {crate.dir: crate for crate in crates}
    for crate in crates:
        for import_name, kind, target, renamed, built, line in listed[crate.manifest]:
            other = by_dir.get(target) if kind == "internal" else None
            # Code names a dependency by its library's name, which [lib] name can
            # set, unless the manifest renames the dependency.
            if other is not None and not renamed:
                import_name = other.name
            crate.deps.setdefault(import_name, (kind, target))
            if built:
                crate.declared.append((import_name, line))
    crates.sort(key=lambda c: len(c.dir), reverse=True)  # nearest crate first
    return crates


def _crate_of(crates: list[Crate], path: str) -> Crate | None:
    for crate in crates:
        if not crate.dir or path.startswith(crate.dir + "/"):
            return crate
    return None


def _module_of(crate: Crate, path: str) -> tuple[str, ...] | None:
    """The module a file is, or None when it is not part of the library's module tree."""
    prefix = crate.src + "/" if crate.src not in ("", ".") else ""
    if not path.startswith(prefix):
        return None
    parts = path[len(prefix) : -len(".rs")].split("/")
    if parts[0] == "bin":
        return None
    if parts[-1] == "mod" or parts in (["lib"], ["main"]):
        parts = parts[:-1]
    return tuple(parts)


def _longest(modules: dict[tuple[str, ...], str], segments: list[str]) -> str | None:
    for length in range(len(segments), -1, -1):
        found = modules.get(tuple(segments[:length]))
        if found:
            return found
    return None


def extract(root: str, files: list[str], include_tests: bool, scan: Scan) -> None:
    crates = discover(root, files, scan)
    by_dir = {crate.dir: crate for crate in crates}
    sources = [path for path in files if path.endswith(".rs")]
    owner = {path: _crate_of(crates, path) for path in sources}

    for path in sources:
        crate = owner[path]
        if crate is None:
            continue
        module = _module_of(crate, path)
        if module is not None and not (module == () and () in crate.modules and path.endswith("main.rs")):
            crate.modules[module] = path

    for crate in crates:
        scan.files.append(crate.manifest)
        for import_name, line in crate.declared:
            kind, target = crate.deps[import_name]
            other = by_dir.get(target) if kind == "internal" else None
            if other is not None:
                scan.refs.append(Ref(crate.manifest, line, "internal", other.manifest, f"dependency {other.package}"))
            else:
                package = posixpath.basename(target) if kind == "internal" else target
                scan.refs.append(Ref(crate.manifest, line, "external", package, package))

    for path in sources:
        crate = owner[path]
        if crate is None:
            scan.warnings.append(f"{path}: no Cargo.toml above it, skipped")
            continue
        if not include_tests and _is_test(crate, path):
            continue
        scan.files.append(path)
        _file(root, path, crate, by_dir, include_tests, scan)


def _file(root: str, path: str, crate: Crate, by_dir: dict[str, Crate], include_tests: bool, scan: Scan) -> None:
    code = strip(read(root, path))
    if not include_tests:
        code = drop_test_modules(code)
    starts = [0] + [m.end() for m in re.finditer("\n", code)]

    def line(position: int) -> int:
        return bisect.bisect_right(starts, position)

    current = _module_of(crate, path) or ()
    found: list[tuple[int, list[str]]] = []
    for match in _USE.finditer(code):
        found.extend((match.start(), segments) for segments in expand_use(match.group(1)))
    # Paths inside `use` are done; keep them out of the scan for qualified paths.
    rest = _USE.sub(lambda m: "".join(ch if ch == "\n" else " " for ch in m.group(0)), code)
    for match in _EXTERN.finditer(rest):
        found.append((match.start(), [match.group(1)]))
    for match in _PATH.finditer(rest):
        found.append((match.start(), re.split(r"\s*::\s*", match.group(1))))

    for position, segments in found:
        ref = _resolve(path, line(position), segments, current, crate, by_dir)
        if ref is not None and ref.target != path:
            scan.refs.append(ref)

    for pattern, name in _EFFECTS:
        for match in pattern.finditer(code):
            scan.refs.append(Ref(path, line(match.start()), "effect", name(match), name(match)))


def _resolve(
    path: str, line: int, segments: list[str], current: tuple[str, ...], crate: Crate, by_dir: dict[str, Crate]
) -> Ref | None:
    written = "::".join(segments)
    head = segments[0]
    if head in ("crate", "self", "super"):
        base = [] if head == "crate" else list(current)
        rest = segments[1:]
        if head == "super":
            base = base[:-1]
            while rest and rest[0] == "super":
                base, rest = base[:-1], rest[1:]
        target = _longest(crate.modules, base + rest)
        return Ref(path, line, "internal", target, written) if target else None
    if head == crate.name and head not in crate.deps:
        target = _longest(crate.modules, segments[1:])
        return Ref(path, line, "internal", target, written) if target else None
    if head in crate.deps:
        kind, target = crate.deps[head]
        other = by_dir.get(target) if kind == "internal" else None
        if other is not None:
            return Ref(path, line, "internal", _longest(other.modules, segments[1:]) or other.root_file(), written)
        package = posixpath.basename(target).replace("-", "_") if kind == "internal" else target
        return Ref(path, line, "external", package, "::".join([package] + segments[1:]))
    if head in STD:
        return Ref(path, line, "external", head, written)
    # A child module named without `self::`, as in `use child::Thing;`.
    if tuple(current) + (head,) in crate.modules:
        target = _longest(crate.modules, list(current) + segments)
        return Ref(path, line, "internal", target, written) if target else None
    return None
