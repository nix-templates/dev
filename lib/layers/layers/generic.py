"""Reading a language from its text.

Most languages are read the same way: blank the comments and the inside of
strings, find the statements that name another module, and work out which file
that name means. This file holds that machinery; languages.py describes each
language with it.

It is close, not exact. Nothing is compiled, so names built at run time,
macros and build-system path mappings are not followed.
"""

import bisect
import os
import posixpath
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache

from .config import Config
from .model import Ref, Scan
from .walk import read

TEST_DIRS = frozenset({"test", "tests", "spec", "specs", "__tests__", "testdata", "e2e", "t"})
TEST_NAME = re.compile(r"^test_|^tb_|_test\.|_tb\.|\.test\.|_spec\.|\.spec\.|Tests?\.\w+$|Spec\.\w+$")


def is_test(path: str) -> bool:
    parts = path.split("/")
    return any(part.lower() in TEST_DIRS for part in parts[:-1]) or bool(TEST_NAME.search(parts[-1]))


@dataclass(frozen=True)
class Syntax:
    """Where a language's comments and strings begin and end."""

    line: tuple[str, ...] = ("//",)
    block: tuple[tuple[str, str], ...] = (("/*", "*/"),)
    nested: bool = False  # block comments nest
    quotes: str = '"'
    multiline: str = ""  # the quotes whose strings may span lines
    triple: bool = False  # three quotes open a string that ends at the next three
    spaced: bool = False  # a line comment starts only at the start of a line or after white space


def _spaces(segment: str) -> str:
    """As many spaces as the segment is long, with its line breaks kept."""
    if "\n" not in segment:
        return " " * len(segment)
    return "\n".join(" " * len(piece) for piece in segment.split("\n"))


@lru_cache(maxsize=None)
def _scanner(syntax: Syntax) -> re.Pattern[str] | None:
    """Finds the next place a comment or a string can start. Longer markers win."""
    tokens = sorted({pair[0] for pair in syntax.block} | set(syntax.line) | set(syntax.quotes), key=len, reverse=True)
    return re.compile("|".join(re.escape(token) for token in tokens)) if tokens else None


@lru_cache(maxsize=None)
def _nesting(opening: str, closing: str) -> re.Pattern[str]:
    return re.compile(f"{re.escape(closing)}|{re.escape(opening)}")


@lru_cache(maxsize=None)
def _string_body(quote: str, multiline: bool) -> re.Pattern[str]:
    stop = re.escape(quote) + "\\\\" + ("" if multiline else "\n")
    return re.compile(f"(?:[^{stop}]|\\\\.)*", re.S)


def blank(text: str, syntax: Syntax) -> str:
    """text with comments and the inside of strings turned into spaces.

    The result has the same length and the same line breaks, so a position in
    it is a position in text, and the quotes themselves stay where they were.
    """
    scanner = _scanner(syntax)
    if scanner is None:
        return text
    blocks = dict(syntax.block)
    parts: list[str] = []
    n = len(text)
    last = i = 0

    def wipe(begin: int, stop: int) -> None:
        nonlocal last
        parts.append(text[last:begin])
        parts.append(_spaces(text[begin:stop]))
        last = stop

    while True:
        found = scanner.search(text, i)
        if not found:
            break
        i = found.start()
        token = found.group(0)
        if token in blocks:
            closing = blocks[token]
            j = i + len(token)
            if syntax.nested and token != closing:
                depth = 1
                both = _nesting(token, closing)
                while depth:
                    step = both.search(text, j)
                    if not step:
                        j = n
                        break
                    depth += -1 if step.group(0) == closing else 1
                    j = step.end()
            else:
                stop = text.find(closing, j)
                j = n if stop < 0 else stop + len(closing)
            wipe(i, j)
            i = j
        elif token in syntax.line:
            if syntax.spaced and i > 0 and text[i - 1] not in " \t\n;":
                i += 1
                continue
            stop = text.find("\n", i)
            stop = n if stop < 0 else stop
            wipe(i, stop)
            i = stop
        elif syntax.triple and text.startswith(token * 3, i):
            stop = text.find(token * 3, i + 3)
            stop = n if stop < 0 else stop
            wipe(i + 3, stop)
            i = stop + 3
        else:
            stop = _string_body(token, token in syntax.multiline).match(text, i + 1).end()
            wipe(i + 1, stop)
            i = stop + 1
    parts.append(text[last:])
    return "".join(parts)


class Source:
    """One file: its text, and the same text with comments and strings blanked."""

    def __init__(self, path: str, text: str, syntax: Syntax):
        self.path = path
        self.text = text
        self.syntax = syntax
        self.bare = blank(text, syntax)
        self._breaks: list[int] | None = None

    def line(self, position: int) -> int:
        if self._breaks is None:
            self._breaks = [match.start() for match in re.finditer("\n", self.text)]
        return bisect.bisect_left(self._breaks, position) + 1

    def literal(self, position: int) -> str:
        """The string whose opening quote is at position."""
        end = self.bare.find(self.bare[position], position + 1)
        return self.text[position + 1 : end if end >= 0 else len(self.text)]

    def literals(self, begin: int, end: int) -> list[tuple[int, str]]:
        """Every string between two positions, with where it starts."""
        found = []
        i = begin
        while i < end:
            if self.bare[i] in self.syntax.quotes:
                close = self.bare.find(self.bare[i], i + 1)
                if close < 0:
                    break
                found.append((i, self.text[i + 1 : close]))
                i = close + 1
            else:
                i += 1
        return found

    def restore(self, begin: int, end: int) -> str:
        """The code between two positions with its strings as written, comments still blank."""
        out = list(self.bare[begin:end])
        for position, content in self.literals(begin, end):
            out[position + 1 - begin : position + 1 - begin + len(content)] = content
        return "".join(out)

    def spec(self, match: re.Match[str]) -> str:
        """What a statement names: the string at group q, else the text of group spec."""
        groups = match.groupdict()
        if groups.get("q"):
            return self.literal(match.start("q"))
        if groups.get("spec") is None:
            return ""
        return self.restore(match.start("spec"), match.end("spec")).strip()


class Repo:
    """What every reader needs: the files, and where to put what it finds."""

    def __init__(self, root: str, files: list[str], config: Config, scan: Scan):
        self.root = root
        self.files = files
        self.known = frozenset(files)
        self.config = config
        self.scan = scan
        directories = {""}
        for path in files:
            directory = posixpath.dirname(path)
            while directory and directory not in directories:
                directories.add(directory)
                directory = posixpath.dirname(directory)
        self.dirs = frozenset(directories)
        self._texts: dict[str, str] = {}
        self._inside: dict[str, list[str]] | None = None
        self._named: dict[str, list[str]] | None = None

    def text(self, path: str) -> str:
        if path not in self._texts:
            self._texts[path] = read(self.root, path)
        return self._texts[path]

    def inside(self, directory: str) -> list[str]:
        """The files directly in a directory."""
        if self._inside is None:
            self._inside = {}
            for path in self.files:
                self._inside.setdefault(posixpath.dirname(path), []).append(path)
        return self._inside.get(directory.strip("/"), [])

    def below(self, directory: str) -> list[str]:
        directory = directory.strip("/")
        return [path for path in self.files if not directory or path.startswith(directory + "/")]

    def named(self, *names: str) -> list[str]:
        """The files with one of these names, wherever they are."""
        if self._named is None:
            self._named = {}
            for path in self.files:
                self._named.setdefault(posixpath.basename(path), []).append(path)
        return [path for name in names for path in self._named.get(name, [])]

    def internal(self, file: str, line: int, targets: Iterable[str], written: str) -> None:
        """A use of files in the repository: one reference for each layer they are in."""
        layers = set()
        for target in sorted(set(targets)):
            if target == file:
                continue
            layer = self.config.layer_of(target)
            name = layer.name if layer else None
            if name not in layers:
                layers.add(name)
                self.scan.refs.append(Ref(file, line, "internal", target, written))

    def external(self, file: str, line: int, package: str, written: str) -> None:
        self.scan.refs.append(Ref(file, line, "external", package, written))

    def effect(self, file: str, line: int, name: str, written: str = "") -> None:
        self.scan.refs.append(Ref(file, line, "effect", name, written or name))


Reader = Callable[[Repo, "Language", list[Source], list[Source]], None]


@dataclass(frozen=True)
class Language:
    name: str
    extensions: tuple[str, ...]
    syntax: Syntax
    readers: tuple[Reader, ...]
    # What a pure layer may not touch: calls and statements, and packages.
    effects: tuple[tuple[str, str], ...] = ()
    impure: tuple[str, ...] = ()
    allowed: tuple[str, ...] = ()
    # For an extension two languages share: does this file belong to this one?
    accepts: Callable[[str, str], bool] | None = None
    # Files with no extension count when their first line matches this.
    shebang: str | None = None
    # Turns text the scanner would misread into spaces, keeping every position.
    prepare: Callable[[str], str] | None = None


def nearest(candidates: list[str], importer: str) -> str:
    """The candidate that shares the longest directory path with the importer."""
    here = posixpath.dirname(importer).split("/")

    def shared(path: str) -> int:
        there = posixpath.dirname(path).split("/")
        count = 0
        for a, b in zip(here, there):
            if a != b:
                break
            count += 1
        return count

    return max(sorted(candidates), key=shared)


def first_segment(spec: str) -> str:
    """An external's package: its first segment, or two for a scoped name such as @scope/name."""
    parts = re.split(r"[/.\\]|::", spec.lstrip("./\\"))
    if spec.startswith("@") and "/" in spec:
        return "/".join(spec.split("/")[:2])
    return parts[0] if parts and parts[0] else spec


def expand(spec: str, sep: str) -> list[str]:
    """`a.b.{C, D}`, `a.b.*` and `a.b._` as the plain names they stand for."""
    spec = spec.strip()
    group = re.match(r"^(.*?)\{(.*)\}$", spec, re.S)
    if group:
        prefix = group.group(1).strip().rstrip(".\\:")
        names = []
        for item in group.group(2).split(","):
            found = re.match(r"\s*([\w.\\:]+)", item)
            if not found or found.group(1) in ("_", "self"):
                names.append(prefix)
            else:
                names.append(prefix + sep + found.group(1))
        return list(dict.fromkeys(names))
    return [re.sub(r"(?:\.|\\|::)(?:\*|_)$", "", spec)]


def namespaces(
    declare: str | Callable[[Source], Iterable[str]],
    *imports: str,
    sep: str = ".",
    members: bool = True,
    type_files: bool = False,
    parents: bool = False,
    fold: bool = False,
    drop: tuple[str, ...] = (),
    qualified: str | None = None,
    member_sep: str = ".",
    package: Callable[[str], str] | None = None,
    externals: bool = True,
) -> Reader:
    """A reader for languages whose files say which namespace they are.

    declare finds the names a file declares (group 1). imports find what a
    file uses (group spec, or the string at group q). qualified finds names
    used without an import (group 1, with an optional member in group 2).

    members: a name may point inside a namespace, so its longest declared
    prefix counts. type_files: `a.b.Type` is the file Type.<ext> in a.b when
    there is one. parents: declaring a.b.C also puts the file in a.b.
    """
    declared = None if callable(declare) else re.compile(declare, re.M)
    patterns = [re.compile(pattern, re.M) for pattern in imports]
    loose = re.compile(qualified, re.M) if qualified else None

    def norm(name: str) -> str:
        name = name.strip().strip(sep)
        if fold:
            name = name.lower()
        for prefix in drop:
            if name.startswith(prefix):
                name = name[len(prefix) :]
        return name

    def reader(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
        index: dict[str, list[str]] = {}
        types: dict[tuple[str, str], str] = {}
        for source in everything:
            names = declare(source) if callable(declare) else (match.group(1) for match in declared.finditer(source.bare))
            stem = posixpath.basename(source.path).split(".")[0]
            for name in dict.fromkeys(norm(name) for name in names):
                if not name:
                    continue
                index.setdefault(name, []).append(source.path)
                if parents and sep in name:
                    index.setdefault(name.rsplit(sep, 1)[0], []).append(source.path)
                if type_files:
                    types[(name, stem)] = source.path

        for source in checked:
            seen: set[str] = set()

            def use(position: int, name: str, member: str = "") -> None:
                name = norm(name)
                written = name + (member_sep + member if member else "")
                if not name or written in seen:
                    return
                seen.add(written)
                line = source.line(position)
                parts = name.split(sep)
                for length in range(len(parts), 0, -1) if members else (len(parts),):
                    files = index.get(sep.join(parts[:length]))
                    if files:
                        rest = parts[length:]
                        exact = types.get((sep.join(parts[:length]), rest[0])) if type_files and rest else None
                        repo.internal(source.path, line, [exact] if exact else files, written)
                        return
                if externals:
                    repo.external(source.path, line, package(name) if package else parts[0], written)

            for pattern in patterns:
                for match in pattern.finditer(source.bare):
                    for name in expand(source.spec(match), sep):
                        use(match.start(), name)
            if loose:
                for match in loose.finditer(source.bare):
                    member = match.group(2) if (match.lastindex or 0) >= 2 and match.group(2) else ""
                    use(match.start(), match.group(1), member)

    return reader


def paths(
    *imports: str,
    extensions: tuple[str, ...] = (),
    index: tuple[str, ...] = (),
    dotted: str | None = None,
    relative: str = "first",
    roots: tuple[str, ...] = ("",),
    manifests: tuple[str, ...] = (),
    directory: bool = False,
    loose: bool = True,
    split: Callable[[str], Iterable[str]] | None = None,
    is_path: Callable[[str], bool] | None = None,
    package: Callable[[str], str] | None = None,
    externals: bool = True,
) -> Reader:
    """A reader for languages that name what they use by where it is.

    imports find the statements (the string at group q, or group spec).
    dotted: the separator when a name is written a.b.c for a/b/c.
    relative: "first" looks beside the importing file before the roots, "last"
    after them, "dot" only for names that start with ./ or ../, "never" not at
    all.
    roots are tried in turn, each also below every directory that holds one
    of the manifests. directory: a name may be a directory of sources.
    loose: a name of two or more segments may match the end of a path.
    is_path: when it says no, the name is an external without looking.
    """
    patterns = [re.compile(pattern, re.M) for pattern in imports]

    def reader(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
        mine = [source.path for source in everything]
        bases = [""] + sorted({posixpath.dirname(path) for path in repo.named(*manifests)} - {""}) if manifests else [""]
        places = list(
            dict.fromkeys(
                [root.strip("/") for root in repo.config.roots]
                + [posixpath.normpath(posixpath.join(base, root)) for base in bases for root in roots]
            )
        )
        places = ["" if place == "." else place for place in places]
        by_stem: dict[str, list[str]] = {}
        for path in mine:
            by_stem.setdefault(posixpath.basename(path).split(".")[0], []).append(path)
            if posixpath.basename(path) in index:
                by_stem.setdefault(posixpath.basename(posixpath.dirname(path)), []).append(path)

        def find(candidate: str) -> list[str] | None:
            candidate = posixpath.normpath(candidate)
            if candidate.startswith(".."):
                return None
            candidate = "" if candidate == "." else candidate
            if candidate in repo.known:
                return [candidate]
            for extension in extensions:
                if candidate + extension in repo.known:
                    return [candidate + extension]
            for name in index:
                inside = posixpath.join(candidate, name)
                if inside in repo.known:
                    return [inside]
            if directory and candidate in repo.dirs:
                files = [path for path in repo.inside(candidate) if path.endswith(language.extensions)]
                if files:
                    return files
            return None

        def by_suffix(name: str, importer: str) -> list[str] | None:
            hits = []
            for path in by_stem.get(name.rsplit("/", 1)[-1], []):
                stem = path
                if posixpath.basename(path) in index:
                    stem = posixpath.dirname(path)
                else:
                    for extension in extensions:
                        if path.endswith(extension):
                            stem = path[: -len(extension)]
                            break
                if stem == name or stem.endswith("/" + name):
                    hits.append(path)
            return [nearest(hits, importer)] if hits else None

        def resolve(source: Source, position: int, written: str) -> None:
            written = written.strip()
            if not written:
                return
            line = source.line(position)
            if is_path and not is_path(written):
                if externals:
                    repo.external(source.path, line, package(written) if package else first_segment(written), written)
                return
            here = posixpath.dirname(source.path)
            if written.endswith(("/*", "/**")):
                base = posixpath.normpath(posixpath.join(here, written.rstrip("*").rstrip("/")))
                files = repo.below(base) if written.endswith("**") else repo.inside(base)
                repo.internal(source.path, line, [p for p in files if p.endswith(language.extensions)], written)
                return
            dot = written.startswith(("./", "../"))
            name = written if dotted is None or dot else written.replace(dotted, "/")
            name = name.lstrip("/") if not dot else name
            found = None
            if dot or relative == "first":
                found = find(posixpath.join(here, name))
            if found is None and not dot:
                ordered = sorted(places, key=lambda place: (not (not place or source.path.startswith(place + "/")), -len(place)))
                for place in ordered:
                    found = find(posixpath.join(place, name))
                    if found:
                        break
            if found is None and not dot and relative == "last":
                found = find(posixpath.join(here, name))
            if found is None and not dot and loose and "/" in name:
                found = by_suffix(name, source.path)
            if found:
                repo.internal(source.path, line, found, written)
            elif not dot and externals:
                repo.external(source.path, line, package(written) if package else first_segment(written), written)

        for source in checked:
            for pattern in patterns:
                for match in pattern.finditer(source.bare):
                    spec = source.spec(match)
                    for item in split(spec) if split else (spec,):
                        resolve(source, match.start(), item)

    return reader


def close_of(text: str, start: int) -> int:
    """The position after the bracket that closes the one at start."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] in "([{":
            depth += 1
        elif text[i] in ")]}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def extract(
    root: str,
    files: list[str],
    languages: Iterable[Language],
    config: Config,
    scan: Scan,
    scripts: dict[str, str] | None = None,
) -> None:
    """Read every language in languages. scripts is first_lines(root, files), when the caller has it."""
    repo = Repo(root, files, config, scan)
    by_extension: dict[str, list[str]] = {}
    for path in files:
        name = posixpath.basename(path)
        if "." in name:
            by_extension.setdefault("." + name.rsplit(".", 1)[1], []).append(path)
    for language in languages:
        mine = [path for extension in language.extensions for path in by_extension.get(extension, [])]
        if language.shebang:
            if scripts is None:
                scripts = first_lines(root, files)
            wanted = re.compile(language.shebang)
            mine += [path for path, first in scripts.items() if wanted.search(first)]
        if language.accepts:
            mine = [path for path in mine if language.accepts(path, repo.text(path))]
        if not mine:
            continue
        everything = []
        for path in sorted(mine):
            text = repo.text(path)
            everything.append(Source(path, language.prepare(text) if language.prepare else text, language.syntax))
        checked = [source for source in everything if config.include_tests or not is_test(source.path)]
        scan.tests.update(source.path for source in everything if source not in checked)
        for source in checked:
            scan.files.append(source.path)
            scan.language[source.path] = language.name
        for reader in language.readers:
            reader(repo, language, everything, checked)
        for pattern, name in language.effects:
            compiled = re.compile(pattern, re.M)
            for source in checked:
                for match in compiled.finditer(source.bare):
                    repo.effect(source.path, source.line(match.start()), name, match.group(0).strip())


def first_lines(root: str, files: list[str]) -> dict[str, str]:
    """The first line of every file that has no extension and starts with #!.

    A script is read as the language its first line names.
    """
    found = {}
    for path in files:
        if "." in posixpath.basename(path):
            continue
        try:
            with open(os.path.join(root, path), "rb") as handle:
                head = handle.read(120)
        except OSError:
            continue
        if head.startswith(b"#!"):
            found[path] = head.split(b"\n", 1)[0].decode("utf-8", "replace")
    return found
