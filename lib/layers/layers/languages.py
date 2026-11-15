"""The languages that are read from their text, each described with generic.py.

An entry says how the language's comments and strings look, how a file names
what it uses, how that name leads to a file, and what a pure layer may not
touch. Rust, Python, JavaScript/TypeScript and C/C++ have readers of their
own, next to this file.
"""

import posixpath
import re
from collections.abc import Iterable

from . import effects
from .generic import (
    Language,
    Reader,
    Repo,
    Source,
    Syntax,
    close_of,
    namespaces,
    nearest,
    paths,
)

# --- how comments and strings look -------------------------------------------

C = Syntax(quotes="\"'")
C_NESTED = Syntax(quotes="\"'", nested=True, triple=True)
C_TRIPLE = Syntax(quotes="\"'", triple=True)
HASH = Syntax(line=("#",), block=(), quotes="\"'", multiline="\"'", spaced=True)
DASHES = Syntax(line=("--",), block=(("{-", "-}"),), nested=True, quotes='"', triple=True)
LISP = Syntax(line=(";",), block=(("#|", "|#"),), nested=True, quotes='"', multiline='"')


def _commas(spec: str) -> list[str]:
    return [item.strip() for item in spec.split(",") if item.strip()]


def uses(*patterns: str, prefix: str = "", member_sep: str = ".") -> Reader:
    """Names that are never in the repository: group 1 is the package, group 2 (optional) something in it."""
    compiled = [re.compile(pattern, re.M) for pattern in patterns]

    def reader(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
        for source in checked:
            for pattern in compiled:
                for match in pattern.finditer(source.bare):
                    package = prefix + match.group(1)
                    member = match.group(2) if (match.lastindex or 0) >= 2 and match.group(2) else ""
                    repo.external(source.path, source.line(match.start()), package, package + (member_sep + member if member else ""))

    return reader


# --- Go and CUE: an import path is the module's path plus a directory ---------


def _by_module(repo: Repo, everything: list[Source], modules: dict[str, str]) -> dict[str, list[str]]:
    packages: dict[str, list[str]] = {}
    for source in everything:
        directory = posixpath.dirname(source.path)
        base = directory
        while base and base not in modules:
            base = posixpath.dirname(base)
        if base not in modules:
            continue
        inside = directory[len(base) :].strip("/")
        packages.setdefault(modules[base] + ("/" + inside if inside else ""), []).append(source.path)
    return packages


def _go(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    modules = {}
    for path in repo.named("go.mod"):
        found = re.search(r"^module\s+(\S+)", repo.text(path), re.M)
        if found:
            modules[posixpath.dirname(path)] = found.group(1).strip('"')
    packages = _by_module(repo, everything, modules)
    statement = re.compile(r"^\s*import\s*(\(|(?:[\w.]+\s+)?[\"`])", re.M)
    for source in checked:
        for match in statement.finditer(source.bare):
            if match.group(1) == "(":
                end = source.bare.find(")", match.end())
                specs = source.literals(match.end(), end if end >= 0 else len(source.bare))
            else:
                specs = [(match.end() - 1, source.literal(match.end() - 1))]
            for position, spec in specs:
                line = source.line(position)
                files = packages.get(spec)
                if files:
                    repo.internal(source.path, line, [f for f in files if not f.endswith("_test.go")] or files, spec)
                else:
                    parts = spec.split("/")
                    repo.external(source.path, line, "/".join(parts[:3]) if "." in parts[0] else parts[0], spec)


def _cue(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    modules = {}
    for path in repo.named("module.cue"):
        if posixpath.basename(posixpath.dirname(path)) != "cue.mod":
            continue
        found = re.search(r'^module:\s*"([^"@]+)', repo.text(path), re.M)
        if found:
            modules[posixpath.dirname(posixpath.dirname(path))] = found.group(1)
    packages = _by_module(repo, everything, modules)
    statement = re.compile(r"^\s*import\s*(\(|(?:\w+\s+)?\")", re.M)
    for source in checked:
        for match in statement.finditer(source.bare):
            if match.group(1) == "(":
                end = source.bare.find(")", match.end())
                specs = source.literals(match.end(), end if end >= 0 else len(source.bare))
            else:
                specs = [(match.end() - 1, source.literal(match.end() - 1))]
            for position, spec in specs:
                name = spec.split(":")[0]
                files = packages.get(name)
                if files:
                    repo.internal(source.path, source.line(position), files, spec)
                else:
                    repo.external(source.path, source.line(position), name.split("/")[0], name)


# --- Swift: a file imports a target, and a target is a directory --------------


def _swift(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    targets: dict[str, list[str]] = {}
    for source in everything:
        parts = source.path.split("/")
        for i, part in enumerate(parts[:-2]):
            if part in ("Sources", "Tests"):
                targets.setdefault(parts[i + 1], []).append(source.path)
                break
    statement = re.compile(
        r"^\s*(?:@\w+(?:\([^)\n]*\))?\s+)*import\s+(?:(?:typealias|struct|class|enum|protocol|let|var|func)\s+)?(\w+)", re.M
    )
    for source in checked:
        for match in statement.finditer(source.bare):
            name = match.group(1)
            line = source.line(match.start(1))
            if name in targets:
                repo.internal(source.path, line, targets[name], name)
            else:
                repo.external(source.path, line, name, name)


# --- Dart: relative paths, and package: for the project's own lib/ ------------


def _dart(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    packages = {}
    for path in repo.named("pubspec.yaml"):
        found = re.search(r"^name:\s*['\"]?(\w+)", repo.text(path), re.M)
        if found:
            packages[found.group(1)] = posixpath.dirname(path)
    statement = re.compile(r"^\s*(?:import|export|part)\s+(?P<q>[\"'])", re.M)
    for source in checked:
        here = posixpath.dirname(source.path)
        for match in statement.finditer(source.bare):
            spec = source.literal(match.start("q"))
            line = source.line(match.start())
            if spec.startswith("dart:"):
                repo.external(source.path, line, spec, spec)
            elif spec.startswith("package:"):
                name, _, rest = spec[len("package:") :].partition("/")
                if name in packages:
                    target = posixpath.normpath(posixpath.join(packages[name], "lib", rest))
                    if target in repo.known:
                        repo.internal(source.path, line, [target], spec)
                else:
                    repo.external(source.path, line, "package:" + name, spec)
            else:
                target = posixpath.normpath(posixpath.join(here, spec))
                if target in repo.known:
                    repo.internal(source.path, line, [target], spec)


# --- Scala, Elixir: what a file declares takes more than one line -------------


def _scala_package(source: Source) -> list[str]:
    names = [match.group(1) for match in re.finditer(r"^\s*package\s+(?!object\b)([\w.]+)", source.bare, re.M)]
    return [".".join(names)] if names else []


def _elixir_modules(source: Source) -> list[str]:
    stack: list[tuple[int, str]] = []
    names = []
    for match in re.finditer(r"^([ \t]*)(?:defmodule|defprotocol)\s+([A-Z][\w.]*)", source.bare, re.M):
        indent = len(match.group(1).expandtabs())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        full = f"{stack[-1][1]}.{match.group(2)}" if stack else match.group(2)
        stack.append((indent, full))
        names.append(full)
    return names


# --- OCaml: a module is a file, and a dune library is a directory -------------


def _ocaml(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    modules: dict[str, list[str]] = {}
    for source in everything:
        stem = posixpath.basename(source.path).split(".")[0]
        modules.setdefault(stem[:1].upper() + stem[1:], []).append(source.path)
    libraries = {}
    for path in repo.named("dune"):
        text = repo.text(path)
        if "(library" in text:
            for found in re.finditer(r"\(name\s+([\w-]+)\)", text):
                name = found.group(1).replace("-", "_")
                libraries[name[:1].upper() + name[1:]] = posixpath.dirname(path)
    name = r"[A-Z][\w']*"
    used = re.compile(
        rf"(?:\b(?:open!?|include)\s+|\bmodule\s+{name}\s*=\s*)({name}(?:\.{name})*)()"
        rf"|(?<![\w.'])({name}(?:\.{name})*)\.([a-z_][\w']*)"
        rf"|(?<![\w.'])({name}(?:\.{name})+)()",
        re.M,
    )
    for source in checked:
        here = posixpath.dirname(source.path)
        seen = set()
        for match in used.finditer(source.bare):
            chain = match.group(1) or match.group(3) or match.group(5)
            member = match.group(4) or ""
            written = chain + ("." + member if member else "")
            if written in seen:
                continue
            seen.add(written)
            parts = chain.split(".")
            line = source.line(match.start())
            if parts[0] in libraries:
                directory = libraries[parts[0]]
                files = [p for p in repo.inside(directory) if p.endswith(language.extensions)]
                if len(parts) > 1:
                    stem = parts[1][:1].lower() + parts[1][1:]
                    exact = [p for p in files if posixpath.basename(p).split(".")[0] == stem]
                    files = exact or files
                repo.internal(source.path, line, files, written)
            elif parts[0] in modules:
                candidates = modules[parts[0]]
                beside = [p for p in candidates if posixpath.dirname(p) == here]
                directories = {posixpath.dirname(p) for p in candidates}
                if beside:
                    repo.internal(source.path, line, beside, written)
                elif len(directories) == 1:
                    repo.internal(source.path, line, candidates, written)
                else:
                    repo.internal(source.path, line, [nearest(candidates, source.path)], written)
            else:
                repo.external(source.path, line, parts[0], written)


# --- Clojure: the ns form ------------------------------------------------------

_CLJ = r"[A-Za-z*+!\-_?<>=][\w*+!\-_?<>=.']*"


def _clojure_libs(body: str) -> list[tuple[int, str]]:
    """The namespaces in the body of a (:require ...): bare symbols, and the first symbol of each vector."""
    found = []
    depth = 0
    first = False
    for match in re.finditer(r"[\[\](){}]|[^\s\[\](){}]+", body):
        token = match.group(0)
        if token in "[(":
            depth += 1
            first = True
        elif token in "])":
            depth -= 1
        elif token in "{}":
            continue
        else:
            if not token.startswith((":", "#", "^", "'")) and (depth == 0 or (depth == 1 and first)):
                found.append((match.start(), token))
            first = False
    return found


def _clojure(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    head = re.compile(r"\(ns\s+(?:\^(?:\{[^}]*\}|\S+)\s+)*(" + _CLJ + ")")
    declared = {}
    for source in everything:
        found = head.search(source.bare)
        if found:
            declared.setdefault(found.group(1), source.path)

    def use(source: Source, position: int, name: str) -> None:
        line = source.line(position)
        if name in declared:
            repo.internal(source.path, line, [declared[name]], name)
        else:
            repo.external(source.path, line, name.split(".")[0], name)

    for source in checked:
        bare = source.bare
        found = head.search(bare)
        if found:
            form_end = close_of(bare, found.start())
            for section in re.finditer(r"\(:(require|use|require-macros|import)\b", bare[found.start() : form_end]):
                begin = found.start() + section.start()
                end = close_of(bare, begin)
                body_start = found.start() + section.end()
                libs = _clojure_libs(bare[body_start : end - 1])
                if section.group(1) == "import":
                    for position, token in libs:
                        # (java.io File) names a package then classes; a bare token is a whole class name.
                        listed = bare[body_start + position - 1 : body_start + position] in ("(", "[")
                        package = token if listed or "." not in token else token.rsplit(".", 1)[0]
                        repo.external(source.path, source.line(body_start + position), package, token)
                else:
                    for position, token in libs:
                        use(source, body_start + position, token)
        for match in re.finditer(r"\(require\s+'\[?\s*(" + _CLJ + ")", bare):
            use(source, match.start(1), match.group(1))


# --- Ruby: requires, and constants that name files the way Zeitwerk does ------


def _camel(part: str) -> str:
    return "".join(piece[:1].upper() + piece[1:] for piece in part.split("_"))


def _ruby(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    constants: dict[str, list[str]] = {}
    for source in everything:
        if not source.path.endswith(".rb"):
            continue
        parts = source.path[: -len(".rb")].split("/")
        for start in range(len(parts)):
            constants.setdefault("::".join(_camel(part) for part in parts[start:]), []).append(source.path)
    roots = [""] + sorted(d for d in repo.dirs if posixpath.basename(d) == "lib") + [r.strip("/") for r in repo.config.roots]
    relative = re.compile(r"\brequire_relative\s*\(?\s*(?P<q>[\"'])")
    required = re.compile(r"\b(?:require|load|autoload\s*\(?\s*:\w+\s*,)\s*\(?\s*(?P<q>[\"'])")
    constant = re.compile(r"(?<![\w:])([A-Z]\w*(?:::[A-Z]\w*)*)")

    def find(candidate: str) -> str | None:
        candidate = posixpath.normpath(candidate)
        for path in (candidate, candidate + ".rb"):
            if path in repo.known:
                return path
        return None

    for source in checked:
        here = posixpath.dirname(source.path)
        for match in relative.finditer(source.bare):
            target = find(posixpath.join(here, source.literal(match.start("q"))))
            if target:
                repo.internal(source.path, source.line(match.start()), [target], source.literal(match.start("q")))
        for match in required.finditer(source.bare):
            spec = source.literal(match.start("q"))
            line = source.line(match.start())
            target = next((hit for hit in (find(posixpath.join(root, spec)) for root in roots) if hit), None)
            if target:
                repo.internal(source.path, line, [target], spec)
            else:
                repo.external(source.path, line, spec.split("/")[0], spec)
        seen = set()
        for match in constant.finditer(source.bare):
            name = match.group(1)
            if name in seen:
                continue
            seen.add(name)
            line = source.line(match.start())
            parts = name.split("::")
            for length in range(len(parts), 0, -1):
                files = constants.get("::".join(parts[:length]))
                # One word is only trusted when one file can be meant.
                if files and (length > 1 or len(files) == 1):
                    repo.internal(source.path, line, [nearest(files, source.path)], name)
                    break
            else:
                if name not in constants:
                    repo.external(source.path, line, parts[0], name)


# --- QML: directories, files, and modules declared in a qmldir ----------------


def _qml(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    modules = {}
    for path in repo.named("qmldir"):
        found = re.search(r"^\s*module\s+([\w.]+)", repo.text(path), re.M)
        if found:
            modules[found.group(1)] = posixpath.dirname(path)
    statement = re.compile(r"^\s*import\s+(?:(?P<q>\")|(?P<spec>[A-Za-z_][\w.]*))", re.M)
    kinds = (".qml", ".js", ".mjs")

    def components(directory: str) -> list[str]:
        return [path for path in repo.inside(directory) if path.endswith(kinds)]

    for source in checked:
        here = posixpath.dirname(source.path)
        for match in statement.finditer(source.bare):
            line = source.line(match.start())
            if match.group("q"):
                spec = source.literal(match.start("q"))
                target = posixpath.normpath(posixpath.join(here, spec))
                target = "" if target == "." else target
                if target in repo.known:
                    repo.internal(source.path, line, [target], spec)
                elif target in repo.dirs:
                    repo.internal(source.path, line, components(target), spec)
                continue
            uri = match.group("spec")
            directory = modules.get(uri)
            if directory is None:
                tail = uri.replace(".", "/")
                hits = [d for d in repo.dirs if (d == tail or d.endswith("/" + tail)) and components(d)]
                directory = hits[0] if len(hits) == 1 else None
            if directory is not None:
                repo.internal(source.path, line, components(directory), uri)
            else:
                repo.external(source.path, line, uri.split(".")[0], uri)


# --- Nix and Dhall: a path written in the code is the import -------------------


def _path_literals(pattern: str, endings: tuple[str, ...], index: tuple[str, ...]) -> Reader:
    literal = re.compile(pattern)

    def reader(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
        for source in checked:
            here = posixpath.dirname(source.path)
            for match in literal.finditer(source.bare):
                candidate = posixpath.normpath(posixpath.join(here, match.group(1)))
                if candidate.startswith(".."):
                    continue
                options = [candidate] + [candidate + ending for ending in endings] + [posixpath.join(candidate, name) for name in index]
                target = next((path for path in options if path in repo.known), None)
                if target:
                    repo.internal(source.path, source.line(match.start(1)), [target], match.group(1))

    return reader


# --- Shell and PowerShell: files that are sourced ------------------------------


def _word(text: str, start: int) -> str:
    """The shell word that starts at start: quotes, $(...) and ${...} keep their spaces."""
    i = start
    n = len(text)
    quote = ""
    while i < n:
        c = text[i]
        if text.startswith("$(", i) or text.startswith("${", i):
            i = close_of(text, i + 1)
            continue
        if quote:
            if c == quote:
                quote = ""
            elif c == "\\" and quote == '"':
                i += 1
        elif c in "\"'":
            quote = c
        elif c in " \t\n;&|)":
            break
        i += 1
    return text[start:i]


def _sourced(statements: tuple[str, ...], endings: tuple[str, ...], named: bool) -> Reader:
    compiled = [re.compile(statement, re.M) for statement in statements]

    def reader(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
        def by_tail(tail: str, importer: str) -> str | None:
            hits = [
                path
                for ending in ("",) + endings
                for path in repo.named(posixpath.basename(tail) + ending)
                if path == tail + ending or path.endswith("/" + tail + ending)
            ]
            return nearest(hits, importer) if hits else None

        for source in checked:
            here = posixpath.dirname(source.path)
            for pattern in compiled:
                for match in pattern.finditer(source.bare):
                    word = _word(source.text, match.end()).replace("\\", "/")
                    plain = word.replace('"', "").replace("'", "")
                    line = source.line(match.start())
                    if not plain or plain.startswith(("/", "~", "-", "<", "(")):
                        continue
                    target = None
                    if "$" in plain or "`" in plain:
                        # A computed directory: only the part after it is known.
                        tail = re.search(r"[})`\w]/((?:\.\./)*[\w.\-]+(?:/[\w.\-]+)*)$", plain)
                        if tail and "$" not in tail.group(1):
                            target = by_tail(posixpath.normpath(tail.group(1)).lstrip("./"), source.path)
                    else:
                        for base in (here, ""):
                            candidate = posixpath.normpath(posixpath.join(base, plain))
                            for ending in ("",) + endings:
                                if candidate + ending in repo.known:
                                    target = candidate + ending
                                    break
                            if target:
                                break
                        if target is None and "/" in plain:
                            target = by_tail(posixpath.normpath(plain).lstrip("./"), source.path)
                        if target is None and named and "/" not in plain and "." not in plain:
                            repo.external(source.path, line, plain, plain)
                    if target:
                        repo.internal(source.path, line, [target], plain)

    return reader


# --- Terraform: a module's source is a directory -------------------------------


def _terraform(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    statement = re.compile(r"^\s*source\s*=\s*(?P<q>\")", re.M)
    for source in checked:
        here = posixpath.dirname(source.path)
        for match in statement.finditer(source.bare):
            spec = source.literal(match.start("q"))
            line = source.line(match.start())
            if spec.startswith(("./", "../")):
                directory = posixpath.normpath(posixpath.join(here, spec))
                repo.internal(source.path, line, [p for p in repo.inside(directory) if p.endswith(language.extensions)], spec)
            else:
                repo.external(source.path, line, spec.split("//")[0].split("?")[0], spec)


# --- Racket: the require form ---------------------------------------------------


def _racket_specs(text: str, bare: str, begin: int, end: int) -> list[tuple[int, str, bool]]:
    """(position, name, is a path) for every module a (require ...) names."""
    tokens = [(m.start() + begin, m.group(0)) for m in re.finditer(r'[()\[\]]|"[^"]*"|[^\s()\[\]"]+', bare[begin:end])]
    found: list[tuple[int, str, bool]] = []

    def parse(i: int) -> tuple[object, int]:
        position, token = tokens[i]
        if token in "([":
            items = []
            i += 1
            while i < len(tokens) and tokens[i][1] not in ")]":
                node, i = parse(i)
                items.append(node)
            return items, i + 1
        return (position, token), i + 1

    def modules(node: object) -> None:
        if isinstance(node, tuple):
            position, token = node
            if token.startswith('"'):
                found.append((position, text[position + 1 : position + len(token) - 1], True))
            elif not token.endswith(":") and not token.startswith(("#", "'")):
                found.append((position, token, False))
            return
        if not node:
            return
        head = node[0][1] if isinstance(node[0], tuple) else ""
        if head in ("only-in", "except-in", "rename-in"):
            rest = node[1:2]
        elif head == "prefix-in":
            rest = node[2:3]
        elif head in ("for-meta", "only-meta-in"):
            rest = node[2:]
        elif head in ("lib", "planet", "submod", "quote"):
            rest = []
        else:
            rest = node[1:]
        for item in rest:
            modules(item)

    i = 0
    while i < len(tokens):
        if tokens[i][1] in (")", "]"):
            i += 1
            continue
        node, i = parse(i)
        modules(node if isinstance(node, list) else [(0, ""), node])
    return found


def _racket(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    for source in checked:
        here = posixpath.dirname(source.path)
        for match in re.finditer(r"\(require\b", source.bare):
            end = close_of(source.bare, match.start())
            for position, name, is_path in _racket_specs(source.text, source.bare, match.end(), end - 1):
                line = source.line(position)
                if is_path:
                    target = posixpath.normpath(posixpath.join(here, name))
                    if target in repo.known:
                        repo.internal(source.path, line, [target], name)
                else:
                    repo.external(source.path, line, name.split("/")[0], name)


# --- Julia: include() for files, using and import for modules -------------------


def _julia(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    declared: dict[str, str] = {}
    for source in everything:
        for match in re.finditer(r"^\s*(?:bare)?module\s+(\w+)", source.bare, re.M):
            declared.setdefault(match.group(1), source.path)
    statement = re.compile(r"^\s*(?:using|import)\s+(?P<spec>[^\n]+)", re.M)
    for source in checked:
        for match in statement.finditer(source.bare):
            line = source.line(match.start())
            for item in match.group("spec").split(","):
                name = item.split(":")[0].strip().lstrip(".")
                name = re.sub(r"\s+as\s+\w+$", "", name)
                if not re.fullmatch(r"[\w.]+", name or ""):
                    continue
                first = name.split(".")[0]
                if first in declared:
                    repo.internal(source.path, line, [declared[first]], name)
                else:
                    repo.external(source.path, line, first, name)


# --- Verilog: a module is used by instantiating it ------------------------------


def _verilog_instances(repo: Repo, language: Language, everything: list[Source], checked: list[Source]) -> None:
    declared = {}
    for source in everything:
        for match in re.finditer(r"^\s*(?:module|interface|program)\s+(?:automatic\s+|static\s+)?(\w+)", source.bare, re.M):
            declared.setdefault(match.group(1), source.path)
    instance = re.compile(r"^\s*(\w+)\s*(?:#\s*\(|\s\w+\s*(?:\[[^\]\n]*\]\s*)?\()", re.M)
    for source in checked:
        for match in instance.finditer(source.bare):
            target = declared.get(match.group(1))
            if target:
                repo.internal(source.path, source.line(match.start(1)), [target], match.group(1))


# --- telling apart the languages that share an extension -----------------------


def _is_prolog(path: str, text: str) -> bool:
    if not path.endswith(".pl"):
        return path.endswith((".pro", ".prolog")) and bool(re.search(r":-", text))
    looks = re.search(r"^\s*:-\s|^[a-z]\w*(?:\([^)\n]*\))?\s*(?::-|-->)|^[a-z]\w*\([^)\n]*\)\s*\.", text, re.M)
    perl = re.search(r"^\s*(?:use\s+(?:strict|warnings|v?5)|my\s+[$@%]|sub\s+\w+|package\s+\w)", text, re.M)
    return bool(looks) and not perl


def _is_verilog(path: str, text: str) -> bool:
    return not path.endswith(".v") or bool(re.search(r"\bend(?:module|package|interface|primitive)\b", text))


def _pod(text: str) -> str:
    """Perl's documentation blocks, as spaces."""
    return re.sub(
        r"(?ms)^=[a-zA-Z].*?(?:^=cut\b[^\n]*|\Z)",
        lambda block: re.sub(r"[^\n]", " ", block.group(0)),
        text,
    )


def _nim_items(spec: str) -> Iterable[str]:
    spec = re.sub(r"\bexcept\b.*", "", spec)
    for match in re.finditer(r'([\w./"]*)/\[([^\]]*)\]|([^,\[\]]+)', spec):
        if match.group(2) is not None:
            items = [f"{match.group(1)}/{item.strip()}" for item in match.group(2).split(",")]
        else:
            items = [match.group(3)]
        for item in items:
            item = re.sub(r"\s+as\s+\w+", "", item).strip().strip('"')
            for prefix in ("std/", "pkg/"):
                item = item.removeprefix(prefix)
            if item:
                yield item


# --- what a pure layer may not touch --------------------------------------------

JVM = (
    "java.io",
    "java.nio.file",
    "java.nio.channels",
    "java.net",
    "java.sql",
    "javax.sql",
    "java.util.concurrent",
    "java.util.Random",
    "java.util.Scanner",
    "java.util.Timer",
    "java.util.logging",
    "java.security.SecureRandom",
    "java.lang.ProcessBuilder",
    "java.lang.Runtime",
    "java.lang.Thread",
    "org.slf4j",
    "org.apache.logging",
    "org.springframework",
    "jakarta.persistence",
    "javax.persistence",
    "okhttp3",
    "retrofit2",
    "kotlin.io",
    "kotlin.concurrent",
    "kotlin.random",
    "kotlinx.coroutines",
    "scala.io",
    "scala.sys",
    "scala.concurrent",
    "scala.util.Random",
    "akka",
    "groovy.sql",
)
JVM_ALLOWED = ("java.io.Serializable", "java.util.concurrent.TimeUnit")
JVM_EFFECTS = (
    (r"\bSystem\s*\.\s*(?:out|err|in)\b", "console"),
    (r"\b(?:println|readLine|readln)\s*\(", "console"),
    (r"\bSystem\s*\.\s*(?:currentTimeMillis|nanoTime)\s*\(", "clock"),
    (r"\b(?:Instant|LocalDate|LocalDateTime|LocalTime|ZonedDateTime|OffsetDateTime|Clock)\s*\.\s*(?:now|systemUTC|systemDefaultZone)\s*\(", "clock"),
    (r"\bSystem\s*\.\s*(?:getenv|getProperty|exit)\s*\(", "environment"),
    (r"\bMath\s*\.\s*random\s*\(|\bnew\s+Random\s*\(|\bUUID\s*\.\s*randomUUID\s*\(", "randomness"),
    (r"\bnew\s+Thread\s*\(|\bThread\s*\.\s*sleep\s*\(", "thread"),
)

DOTNET = (
    "System.IO",
    "System.Net",
    "System.Threading",
    "System.Diagnostics",
    "System.Data",
    "System.Timers",
    "System.Console",
    "System.Environment",
    "System.Random",
    "Microsoft.EntityFrameworkCore",
    "Microsoft.Extensions.Logging",
    "Microsoft.Extensions.Configuration",
    "Microsoft.AspNetCore",
    "Npgsql",
    "Dapper",
)
DOTNET_EFFECTS = (
    (r"\bConsole\s*\.\s*\w+", "console"),
    (r"\bDateTime(?:Offset)?\s*\.\s*(?:Now|UtcNow|Today)\b", "clock"),
    (r"\bEnvironment\s*\.\s*\w+", "environment"),
    (r"\bnew\s+Random\s*\(|\bRandom\s*\.\s*Shared\b|\bGuid\s*\.\s*NewGuid\s*\(", "randomness"),
    (r"\b(?:File|Directory)\s*\.\s*[A-Z]\w*\s*\(", "files"),
    (r"\bTask\s*\.\s*Run\s*\(|\bnew\s+Thread\s*\(|\bThread\s*\.\s*Sleep\s*\(", "thread"),
)

RUBY = (
    "File",
    "IO",
    "Dir",
    "FileUtils",
    "Tempfile",
    "Kernel",
    "Process",
    "Open3",
    "Thread",
    "Mutex",
    "Queue",
    "Socket",
    "TCPSocket",
    "TCPServer",
    "UDPSocket",
    "Net::HTTP",
    "URI.open",
    "SecureRandom",
    "Random",
    "Logger",
    "ENV",
    "ARGV",
    "ARGF",
    "STDIN",
    "STDOUT",
    "STDERR",
    "ObjectSpace",
    "Signal",
    "Faraday",
    "HTTParty",
    "RestClient",
    "Redis",
    "PG",
    "Sequel",
    "ActiveRecord",
    "net/http",
    "socket",
    "open3",
    "open-uri",
    "fileutils",
    "tempfile",
    "logger",
    "securerandom",
)

ELIXIR = (
    "File",
    "IO",
    "System",
    "Port",
    "Process",
    "Node",
    "Agent",
    "GenServer",
    "GenStage",
    "Task",
    "Supervisor",
    "DynamicSupervisor",
    "Registry",
    "Application",
    "Logger",
    "Mix",
    "Code",
    "HTTPoison",
    "Req",
    "Finch",
    "Tesla",
    "Ecto.Repo",
    "Phoenix.PubSub",
    "Oban",
    ":file",
    ":io",
    ":os",
    ":rand",
    ":random",
    ":ets",
    ":dets",
    ":mnesia",
    ":gen_tcp",
    ":gen_udp",
    ":ssl",
    ":httpc",
    ":timer",
    ":persistent_term",
    ":erlang.system_time",
    ":erlang.monotonic_time",
    ":erlang.now",
    ":crypto.strong_rand_bytes",
)

ERLANG = (
    "file",
    "filelib",
    "io",
    "os",
    "gen_tcp",
    "gen_udp",
    "ssl",
    "inet",
    "httpc",
    "ets",
    "dets",
    "mnesia",
    "rand",
    "random",
    "timer",
    "gen_server",
    "gen_statem",
    "gen_event",
    "supervisor",
    "application",
    "logger",
    "error_logger",
    "persistent_term",
    "global",
    "pg",
    "rpc",
    "net_kernel",
    "code",
    "init",
    "disk_log",
    "calendar:local_time",
    "calendar:universal_time",
    "erlang:now",
    "erlang:system_time",
    "erlang:monotonic_time",
    "erlang:timestamp",
    "erlang:send",
    "erlang:spawn",
    "erlang:put",
    "erlang:get",
    "crypto:strong_rand_bytes",
)

HASKELL = (
    "System.IO",
    "System.Directory",
    "System.Process",
    "System.Environment",
    "System.Exit",
    "System.Random",
    "System.Posix",
    "System.Timeout",
    "Data.IORef",
    "Control.Concurrent",
    "Control.Monad.IO.Class",
    "Network",
    "Data.Time.Clock",
    "Debug.Trace",
    "Foreign",
    "GHC.IO",
    "GHC.Conc",
    "Database",
)

LANGUAGES: tuple[Language, ...] = (
    Language(
        "go",
        (".go",),
        Syntax(quotes="\"'`", multiline="`"),
        (_go,),
        effects=(
            (r"\bgo\s+(?:func\b|[\w.]+\s*\()", "goroutine"),
            (r"\bfmt\s*\.\s*(?:Print|Scan)\w*\s*\(", "console"),
            (r"\btime\s*\.\s*(?:Now|Sleep|Since|Until|After|AfterFunc|Tick|NewTimer|NewTicker)\s*\(", "clock"),
        ),
        impure=(
            "os",
            "io/ioutil",
            "net",
            "syscall",
            "math/rand",
            "crypto/rand",
            "sync",
            "database/sql",
            "log",
            "flag",
            "unsafe",
            "runtime",
            "plugin",
            "golang.org/x/sys",
            "google.golang.org/grpc",
            "gorm.io",
            "go.uber.org/zap",
            "github.com/sirupsen/logrus",
            "github.com/jackc/pgx",
            "github.com/lib/pq",
            "github.com/redis/go-redis",
            "github.com/spf13/viper",
        ),
    ),
    Language(
        "java",
        (".java",),
        C_TRIPLE,
        (namespaces(r"^\s*package\s+([\w.]+)", r"^\s*import\s+(?:static\s+)?(?P<spec>[\w.]+(?:\.\*)?)", type_files=True),),
        effects=JVM_EFFECTS,
        impure=JVM,
        allowed=JVM_ALLOWED,
    ),
    Language(
        "kotlin",
        (".kt", ".kts"),
        C_NESTED,
        (namespaces(r"^\s*package\s+([\w.]+)", r"^\s*import\s+(?P<spec>[\w.]+(?:\.\*)?)", type_files=True),),
        effects=JVM_EFFECTS,
        impure=JVM,
        allowed=JVM_ALLOWED,
    ),
    Language(
        "groovy",
        (".groovy",),
        C_TRIPLE,
        (namespaces(r"^\s*package\s+([\w.]+)", r"^\s*import\s+(?:static\s+)?(?P<spec>[\w.]+(?:\.\*)?)", type_files=True),),
        effects=JVM_EFFECTS,
        impure=JVM,
        allowed=JVM_ALLOWED,
    ),
    Language(
        "scala",
        (".scala", ".sc"),
        C_NESTED,
        (
            namespaces(
                _scala_package,
                r"^\s*import\s+(?P<spec>[\w.]+(?:\.\{[^}\n]*\}|\._|\.\*)?)",
                type_files=True,
            ),
        ),
        effects=JVM_EFFECTS,
        impure=JVM,
        allowed=JVM_ALLOWED,
    ),
    Language(
        "csharp",
        (".cs",),
        C_TRIPLE,
        (
            namespaces(
                r"^\s*namespace\s+([\w.]+)",
                r"^\s*(?:global\s+)?using\s+(?:static\s+)?(?:\w+\s*=\s*)?(?P<spec>[A-Za-z_][\w.]*)\s*;",
                type_files=True,
            ),
        ),
        effects=DOTNET_EFFECTS,
        impure=DOTNET,
    ),
    Language(
        "fsharp",
        (".fs", ".fsi", ".fsx"),
        Syntax(block=(("(*", "*)"),), nested=True, quotes='"', triple=True),
        (
            namespaces(
                r"^\s*(?:namespace|module)\s+(?:rec\s+)?(?:global\.)?([A-Z][\w.]*)[ \t]*$",
                r"^\s*open\s+(?:type\s+)?(?:global\.)?(?P<spec>[A-Z][\w.]*)",
                parents=True,
                qualified=r"(?<![\w.])([A-Z]\w*(?:\.[A-Z]\w*)+)",
            ),
        ),
        effects=DOTNET_EFFECTS + ((r"\b(?:printfn?|eprintfn?)\b", "console"),),
        impure=DOTNET,
    ),
    Language(
        "swift",
        (".swift",),
        C_NESTED,
        (_swift,),
        effects=(
            (r"\bprint\s*\(|\breadLine\s*\(", "console"),
            (r"\bDate\s*\(\s*\)|\bDate\s*\.\s*now\b|\bCFAbsoluteTimeGetCurrent\s*\(", "clock"),
            (r"\bFileManager\b|\bFileHandle\b", "files"),
            (r"\bURLSession\b", "network"),
            (r"\bUserDefaults\b|\bNotificationCenter\b", "shared state"),
            (r"\bProcessInfo\b|\bCommandLine\s*\.\s*arguments\b", "environment"),
            (r"\bDispatchQueue\b|\bTask\s*\.\s*detached\b", "thread"),
            (r"\.\s*random\s*\(|\bUUID\s*\(\s*\)|\barc4random\w*\s*\(", "randomness"),
        ),
        impure=("UIKit", "AppKit", "SwiftUI", "Network", "CoreData", "Dispatch", "os", "Combine", "CoreLocation", "WebKit", "SQLite3", "Alamofire", "NIO", "Vapor"),
    ),
    Language(
        "dart",
        (".dart",),
        C_NESTED,
        (_dart,),
        effects=(
            (r"\bDateTime\s*\.\s*now\s*\(", "clock"),
            (r"\bRandom(?:\.secure)?\s*\(", "randomness"),
            (r"\bprint\s*\(|\bstdout\b|\bstdin\b|\bstderr\b", "console"),
            (r"\bTimer(?:\.periodic)?\s*\(", "timer"),
        ),
        impure=(
            "dart:io",
            "dart:html",
            "dart:js",
            "dart:js_interop",
            "dart:ffi",
            "dart:isolate",
            "dart:developer",
            "package:http",
            "package:dio",
            "package:flutter",
            "package:sqflite",
            "package:shared_preferences",
            "package:path_provider",
        ),
    ),
    Language(
        "php",
        (".php",),
        Syntax(line=("//", "#"), quotes="\"'", multiline="\"'"),
        (
            namespaces(
                r"^\s*namespace\s+([\w\\]+)\s*[;{]",
                r"^\s*use\s+(?:function\s+|const\s+)?(?P<spec>\\?[\w\\]+(?:\\\{[^}\n]*\})?)",
                sep="\\",
                type_files=True,
                qualified=r"(?<![\w\\$>:])\\?([A-Z]\w*(?:\\[A-Z]\w*)+)",
                member_sep="\\",
            ),
            paths(
                r"\b(?:require|include)(?:_once)?\s*\(?\s*(?:__DIR__\s*\.\s*)?(?P<q>[\"'])",
                extensions=(".php",),
                loose=False,
                externals=False,
            ),
        ),
        effects=(
            (r"\b(?:file_get_contents|file_put_contents|fopen|fwrite|fread|unlink|mkdir|rmdir|scandir|glob|tempnam|tmpfile)\s*\(", "files"),
            (r"\b(?:curl_\w+|fsockopen|mail|header|setcookie|session_start)\s*\(", "network"),
            (r"\b(?:exec|shell_exec|system|passthru|proc_open|popen)\s*\(", "process"),
            (r"\b(?:time|microtime|hrtime|date|sleep|usleep)\s*\(", "clock"),
            (r"\b(?:rand|mt_rand|random_int|random_bytes|uniqid|shuffle|array_rand)\s*\(", "randomness"),
            (r"\b(?:getenv|putenv)\s*\(|\$_(?:GET|POST|SERVER|COOKIE|SESSION|ENV|FILES|REQUEST)\b", "environment"),
            (r"^\s*(?:echo|print)\b|\b(?:var_dump|print_r|error_log|printf)\s*\(", "console"),
            (r"\bglobal\s+\$|\bstatic\s+\$", "global"),
        ),
        impure=(
            "PDO",
            "GuzzleHttp",
            "Symfony\\Component\\HttpClient",
            "Symfony\\Component\\Filesystem",
            "Symfony\\Component\\Process",
            "Doctrine\\DBAL",
            "Doctrine\\ORM",
            "Illuminate\\Support\\Facades",
            "Illuminate\\Database",
            "Psr\\Log",
            "Monolog",
        ),
    ),
    Language(
        "ruby",
        (".rb", ".rake"),
        Syntax(line=("#",), block=(("\n=begin", "\n=end"),), quotes="\"'", multiline="\"'", spaced=True),
        (_ruby,),
        effects=(
            (r"\b(?:Time|Date|DateTime)\s*\.\s*(?:now|today|current)\b", "clock"),
            (r"^\s*(?:puts|print|pp|warn|gets)\b", "console"),
            (r"\b(?:system|exec|spawn|fork)\s*\(|`", "process"),
            (r"\b(?:rand|srand)\b(?!\s*[=:])", "randomness"),
            (r"(?<![\w$])\$[a-z_]\w*", "global"),
        ),
        impure=RUBY,
    ),
    Language(
        "elixir",
        (".ex", ".exs"),
        Syntax(line=("#",), block=(), quotes="\"'", multiline="\"'", triple=True),
        (
            namespaces(
                _elixir_modules,
                r"^\s*(?:alias|import|use|require)\s+(?P<spec>[A-Z][\w.]*(?:\.\{[^}\n]*\})?)",
                qualified=r"(?<![\w.:@&])([A-Z]\w*(?:\.[A-Z]\w*)*)",
            ),
            uses(r"(?<![\w:]):([a-z]\w*)\.([a-z_]\w*)", prefix=":"),
        ),
        effects=(
            (r"\b(?:DateTime|NaiveDateTime|Date|Time)\s*\.\s*(?:utc_now|now|utc_today|local_now)\b", "clock"),
            (r"\b(?:send|spawn|spawn_link|spawn_monitor)\s*\(|\breceive\s+do\b", "process"),
            (r"\bEnum\s*\.\s*(?:random|shuffle|take_random)\b", "randomness"),
        ),
        impure=ELIXIR,
    ),
    Language(
        "erlang",
        (".erl", ".hrl"),
        Syntax(line=("%",), block=(), quotes='"', multiline='"'),
        (
            namespaces(
                r"^-module\(\s*'?([a-z]\w*)'?\s*\)",
                r"^-(?:import|behaviou?r)\(\s*(?P<spec>[a-z]\w*)",
                members=False,
                qualified=r"(?<![\w:'$?#.])([a-z]\w*):([a-z_]\w*)\s*\(",
                member_sep=":",
            ),
            paths(r"^-include(?:_lib)?\(\s*(?P<q>\")", roots=("", "include", "src"), loose=False),
        ),
        effects=(
            (r"\w\s*!\s*[\w{\[(]|\breceive\b", "process"),
            (r"\bspawn(?:_link|_monitor|_opt)?\s*\(|\bself\s*\(\s*\)", "process"),
        ),
        impure=ERLANG,
    ),
    Language(
        "haskell",
        (".hs",),
        Syntax(line=("--",), block=(("{-", "-}"),), nested=True, quotes='"'),
        (
            namespaces(
                r"^module\s+([A-Z][\w.']*)",
                r"^\s*import\s+(?:safe\s+)?(?:qualified\s+)?(?:\"[^\"\n]*\"\s+)?(?P<spec>[A-Z][\w.']*)",
                members=False,
            ),
        ),
        effects=(
            (r"(?:::|->)\s*IO\b", "IO"),
            (r"\bunsafePerformIO\b|\bunsafeInterleaveIO\b", "unsafePerformIO"),
        ),
        impure=HASKELL,
    ),
    Language(
        "purescript",
        (".purs",),
        DASHES,
        (namespaces(r"^module\s+([A-Z][\w.]*)", r"^\s*import\s+(?P<spec>[A-Z][\w.]*)", members=False),),
        effects=((r"\bunsafePerformEffect\b|\bunsafeCoerce\b", "unsafePerformEffect"),),
        impure=("Effect", "Node", "Web", "Affjax", "Control.Monad.Aff", "Halogen", "React", "Foreign"),
    ),
    Language(
        "elm",
        (".elm",),
        DASHES,
        (namespaces(r"^(?:port\s+|effect\s+)?module\s+([A-Z][\w.]*)", r"^import\s+(?P<spec>[A-Z][\w.]*)", members=False),),
        effects=(
            (r"^port\s+\w+\s*:", "port"),
            (r"\bDebug\s*\.\s*(?:log|todo)\b", "Debug"),
        ),
        impure=("Http", "Browser", "Time", "Random", "Task", "Process", "File", "Platform", "Json.Decode.Value"),
    ),
    Language(
        "ocaml",
        (".ml", ".mli"),
        Syntax(line=(), block=(("(*", "*)"),), nested=True, quotes='"', multiline='"'),
        (_ocaml,),
        effects=(
            (r"\b(?:print_string|print_endline|print_int|print_float|print_newline|prerr_endline|prerr_string|read_line)\b", "console"),
            (r"\b(?:open_in|open_out|open_in_bin|open_out_bin|input_line|output_string|close_in|close_out)\b", "files"),
        ),
        impure=(
            "Unix",
            "Sys",
            "Random",
            "Thread",
            "Mutex",
            "Condition",
            "Domain",
            "Atomic",
            "In_channel",
            "Out_channel",
            "Printf.printf",
            "Printf.eprintf",
            "Format.printf",
            "Format.eprintf",
            "Stdlib.print_endline",
            "Lwt",
            "Lwt_unix",
            "Lwt_io",
            "Async",
            "Eio",
            "Cohttp",
            "Caqti",
            "Logs",
            "Obj",
        ),
    ),
    Language(
        "clojure",
        (".clj", ".cljs", ".cljc", ".bb"),
        Syntax(line=(";",), block=(), quotes='"', multiline='"'),
        (_clojure,),
        effects=(
            (r"\((?:slurp|spit)\b", "files"),
            (r"\((?:println|print|prn|printf|pr|read-line)\b", "console"),
            (r"\((?:rand|rand-int|rand-nth|shuffle|random-uuid)\b", "randomness"),
            (r"\((?:atom|swap!|reset!|ref|agent|alter|dosync|volatile!|vswap!|alter-var-root)\b", "shared state"),
            (r"\((?:future|pmap|pcalls|promise)\b|\bThread/sleep\b", "thread"),
            (r"\bSystem/(?:currentTimeMillis|nanoTime)\b|\(java\.util\.Date\.|\bjs/Date\b", "clock"),
            (r"\bSystem/(?:getenv|getProperty|exit)\b", "environment"),
        ),
        impure=(
            "clojure.java.io",
            "clojure.java.shell",
            "clojure.java.jdbc",
            "clojure.core.async",
            "clojure.tools.logging",
            "next.jdbc",
            "clj-http",
            "org.httpkit",
            "ring",
            "taoensso.timbre",
            "babashka.fs",
            "babashka.process",
            "java.io",
            "java.net",
            "java.nio.file",
            "java.sql",
        ),
    ),
    Language(
        "lua",
        (".lua",),
        Syntax(line=("--",), block=(("--[==[", "]==]"), ("--[=[", "]=]"), ("--[[", "]]")), quotes="\"'"),
        (
            paths(
                r"\brequire\s*\(?\s*(?P<q>[\"'])",
                extensions=(".lua",),
                index=("init.lua",),
                dotted=".",
                relative="never",
                roots=("", "lua", "src", "lib"),
            ),
            paths(r"\b(?:dofile|loadfile)\s*\(\s*(?P<q>[\"'])", loose=False, externals=False),
        ),
        effects=(
            (r"\bio\s*\.\s*\w+", "files"),
            (r"\bos\s*\.\s*(?:execute|getenv|exit|remove|rename|tmpname)\b", "process"),
            (r"\bos\s*\.\s*(?:time|clock|date)\b", "clock"),
            (r"\bprint\s*\(", "console"),
            (r"\bmath\s*\.\s*random(?:seed)?\b", "randomness"),
            (r"\bvim\s*\.\s*(?:fn|api|loop|uv|cmd|system|notify|schedule)\b", "editor"),
        ),
        impure=("socket", "lfs", "posix", "luv", "uv", "ssl", "lsqlite3", "lanes", "http"),
    ),
    Language(
        "perl",
        (".pl", ".pm", ".t"),
        HASH,
        (
            namespaces(
                r"^\s*package\s+([\w:]+)",
                r"^\s*(?:use|require)\s+(?P<spec>[A-Z][\w:]*)",
                r"^\s*use\s+(?:parent|base)\s+(?:-norequire\s*,\s*)?(?P<q>[\"'])",
                sep="::",
                qualified=r"(?<![\w:$@%&>])([A-Z]\w*(?:::\w+)+)",
                member_sep="::",
            ),
        ),
        effects=(
            (r"\b(?:open|opendir|unlink|mkdir|rmdir|rename)\s*\(", "files"),
            (r"\b(?:system|exec|fork)\s*\(|`", "process"),
            (r"^\s*(?:print|say|printf)\b", "console"),
            (r"\b(?:time|localtime|gmtime|sleep)\s*\(", "clock"),
            (r"\b(?:rand|srand)\s*\(", "randomness"),
            (r"\$ENV\{|@ARGV\b|\bSTD(?:IN|OUT|ERR)\b", "environment"),
        ),
        impure=(
            "IO",
            "File",
            "Path::Tiny",
            "Socket",
            "LWP",
            "HTTP::Tiny",
            "Mojo::UserAgent",
            "DBI",
            "Time::HiRes",
            "POSIX",
            "threads",
            "Cwd",
            "IPC",
            "Net",
            "Getopt",
            "Log",
        ),
        accepts=lambda path, text: not _is_prolog(path, text),
        prepare=_pod,
    ),
    Language(
        "r",
        (".R", ".r"),
        Syntax(line=("#",), block=(), quotes="\"'", multiline="\"'"),
        (
            paths(r"\bsource\(\s*(?P<q>[\"'])", relative="last", loose=False, externals=False),
            uses(
                r"\b(?:library|require|requireNamespace|loadNamespace)\(\s*[\"']?\s*([A-Za-z][\w.]*)",
                r"(?<![\w.])([A-Za-z][\w.]*):::?([A-Za-z_.][\w.]*)",
                member_sep="::",
            ),
        ),
        effects=(
            (r"\b(?:read\.\w+|write\.\w+|readLines|writeLines|readRDS|saveRDS|readline|scan|sink|file|url|download\.file|unlink|setwd)\s*\(", "files"),
            (r"\b(?:system|system2)\s*\(", "process"),
            (r"\bSys\.(?:time|Date|sleep)\s*\(|\bdate\s*\(\s*\)", "clock"),
            (r"\bSys\.(?:getenv|setenv)\s*\(|\bcommandArgs\s*\(|\boptions\s*\(", "environment"),
            (r"\b(?:runif|rnorm|rbinom|rpois|sample|set\.seed)\s*\(", "randomness"),
            (r"\b(?:cat|print|message)\s*\(", "console"),
            (r"<<-|\bassign\s*\(", "global"),
        ),
        impure=("httr", "httr2", "curl", "RCurl", "DBI", "RSQLite", "RPostgres", "readr", "readxl", "fs", "processx", "callr", "future", "parallel", "shiny", "plumber", "logger"),
    ),
    Language(
        "julia",
        (".jl",),
        Syntax(line=("#",), block=(("#=", "=#"),), nested=True, quotes='"', triple=True),
        (paths(r"\binclude\(\s*(?P<q>\")", loose=False, externals=False), _julia),
        effects=(
            (r"\b(?:println|print|printstyled|readline|readlines)\s*\(", "console"),
            (r"\b(?:open|download|mkdir|mkpath|rm|cp|mv|cd|pwd|readdir|touch)\s*\(", "files"),
            (r"\b(?:run|exit)\s*\(", "process"),
            (r"\b(?:rand|randn|randstring)\s*\(", "randomness"),
            (r"\b(?:time|time_ns|now|today)\s*\(\s*\)|\bsleep\s*\(", "clock"),
            (r"\bENV\[|\bARGS\b", "environment"),
            (r"@async\b|@spawn\b|@threads\b|@distributed\b", "thread"),
            (r"^\s*global\s", "global"),
        ),
        impure=("Sockets", "Distributed", "Downloads", "HTTP", "Random", "Serialization", "DelimitedFiles", "Mmap", "Libdl", "Logging", "Pkg", "FileWatching", "SharedArrays", "SQLite", "LibPQ"),
    ),
    Language(
        "nim",
        (".nim", ".nims"),
        Syntax(line=("#",), block=(("#[", "]#"),), nested=True, quotes='"', triple=True),
        (
            paths(
                r"^\s*(?:import|include)\s+(?P<spec>[^\n]+)",
                r"^\s*from\s+(?P<spec>[\w./\"]+)\s+import\b",
                extensions=(".nim",),
                roots=("", "src"),
                split=_nim_items,
            ),
        ),
        effects=(
            (r"\becho\b|\b(?:stdout|stdin|stderr)\b|\breadLine\s*\(", "console"),
            (r"\b(?:readFile|writeFile|open)\s*\(", "files"),
            (r"\b(?:now|getTime|epochTime|cpuTime)\s*\(\s*\)", "clock"),
            (r"\b(?:rand|randomize|sample)\s*\(", "randomness"),
            (r"\b(?:getEnv|paramStr|commandLineParams|quit)\s*\(", "environment"),
            (r"\bspawn\b", "thread"),
        ),
        impure=("os", "osproc", "net", "nativesockets", "httpclient", "asynchttpserver", "asyncdispatch", "asyncnet", "random", "threadpool", "locks", "db_sqlite", "db_postgres", "terminal", "logging"),
    ),
    Language(
        "crystal",
        (".cr",),
        Syntax(line=("#",), block=(), quotes='"', multiline='"'),
        (paths(r"^\s*require\s+(?P<q>\")", extensions=(".cr",), relative="dot", roots=(), loose=False),),
        effects=(
            (r"\b(?:File|Dir|FileUtils)\s*\.\s*\w+", "files"),
            (r"\b(?:Process|ENV|ARGV|STDIN|STDOUT|STDERR)\b", "environment"),
            (r"\b(?:TCPSocket|TCPServer|UDPSocket|HTTP::Client|HTTP::Server)\b", "network"),
            (r"^\s*(?:puts|print|pp|gets)\b", "console"),
            (r"\bTime\s*\.\s*(?:utc|local|now|monotonic)\b|\bsleep\b", "clock"),
            (r"\b(?:rand|Random)\b", "randomness"),
            (r"\bspawn\b|\b(?:Fiber|Channel|Mutex)\b", "thread"),
            (r"\bsystem\s*\(|`", "process"),
        ),
        impure=("http", "socket", "file_utils", "log", "db", "sqlite3", "pg", "openssl", "random/secure", "option_parser", "io/console", "tempfile"),
    ),
    Language(
        "zig",
        (".zig",),
        Syntax(block=(), quotes="\"'"),
        (
            paths(
                r"@import\(\s*(?P<q>\")",
                loose=False,
                is_path=lambda spec: "." in posixpath.basename(spec),
                package=lambda spec: spec,
            ),
        ),
        effects=(
            (r"\bstd\s*\.\s*(?:fs|io|net|os|posix|process|http|c)\b", "std.fs"),
            (r"\bstd\s*\.\s*(?:time|Thread)\b", "std.time"),
            (r"\bstd\s*\.\s*(?:rand|Random|crypto\s*\.\s*random)\b", "std.rand"),
            (r"\bstd\s*\.\s*(?:debug\s*\.\s*print|log)\b", "std.debug.print"),
        ),
    ),
    Language(
        "v",
        (".v", ".vsh"),
        Syntax(quotes="\"'", nested=True),
        (
            paths(
                r"^\s*import\s+(?P<spec>[\w.]+)",
                dotted=".",
                directory=True,
                roots=("", "src", "modules", "lib"),
                manifests=("v.mod",),
                loose=False,
            ),
        ),
        effects=(
            (r"\b(?:println|print|eprintln|eprint)\s*\(", "console"),
            (r"\btime\s*\.\s*(?:now|sleep|ticks|utc|sys_mono_now)\s*\(", "clock"),
            (r"\b(?:go|spawn)\s+\w", "thread"),
            (r"\b__global\b", "global"),
        ),
        impure=("os", "net", "rand", "sync", "db", "log", "term", "readline", "vweb", "veb"),
        accepts=lambda path, text: not path.endswith(".v") or not _is_verilog(path, text),
    ),
    Language(
        "odin",
        (".odin",),
        Syntax(quotes="\"'`", multiline="`", nested=True),
        (
            paths(
                r"\bimport\s+(?:\w+\s+)?(?P<q>\")",
                directory=True,
                roots=(),
                loose=False,
                is_path=lambda spec: ":" not in spec,
                package=lambda spec: spec,
            ),
        ),
        effects=(
            (r"\bfmt\s*\.\s*e?print\w*\s*\(", "console"),
            (r"\btime\s*\.\s*(?:now|sleep|tick_now)\s*\(", "clock"),
        ),
        impure=("core:os", "core:net", "core:thread", "core:sync", "core:math/rand", "core:sys", "core:c/libc", "core:log", "vendor"),
    ),
    Language(
        "haxe",
        (".hx",),
        Syntax(quotes="\"'", multiline="\"'"),
        (namespaces(r"^\s*package\s+([\w.]+)\s*;", r"^\s*(?:import|using)\s+(?P<spec>[\w.]+(?:\.\*)?)\s*;", type_files=True),),
        effects=(
            (r"\btrace\s*\(", "console"),
            (r"\bSys\s*\.\s*\w+", "environment"),
            (r"\bDate\s*\.\s*now\s*\(|\bTimer\s*\.\s*stamp\s*\(", "clock"),
            (r"\bMath\s*\.\s*random\s*\(|\bStd\s*\.\s*random\s*\(", "randomness"),
        ),
        impure=("sys", "haxe.Http", "haxe.Timer", "haxe.Log", "js.Browser", "js.html", "js.node", "openfl", "lime", "flixel", "hl", "cpp", "python.lib"),
    ),
    Language(
        "gleam",
        (".gleam",),
        Syntax(block=(), quotes='"', multiline='"'),
        (
            paths(
                r"^\s*import\s+(?P<spec>[a-z][\w/]*)",
                extensions=(".gleam",),
                relative="never",
                roots=("src", "test", "dev"),
                manifests=("gleam.toml",),
                loose=False,
                package=lambda spec: spec.split("/")[0],
            ),
        ),
        effects=(
            (r"@external\s*\(", "external function"),
            (r"\b(?:int|float)\s*\.\s*random\s*\(", "randomness"),
        ),
        impure=("gleam/io", "gleam/erlang", "gleam/otp", "gleam/httpc", "gleam/fetch", "gleam/javascript", "simplifile", "envoy", "argv", "mist", "wisp", "gleam/pgo", "sqlight"),
    ),
    Language(
        "lean",
        (".lean",),
        Syntax(line=("--",), block=(("/-", "-/"),), nested=True, quotes='"', multiline='"'),
        (
            paths(
                r"^\s*(?:public\s+|private\s+)?(?:meta\s+)?import\s+(?:all\s+)?(?P<spec>[A-Z][\w.]*)",
                extensions=(".lean",),
                dotted=".",
                relative="never",
                manifests=("lakefile.lean", "lakefile.toml"),
            ),
        ),
        effects=(
            (r"(?::|→|->)\s*(?:IO|EIO|BaseIO)\b", "IO"),
            (r"\bunsafe\s+(?:def|instance|structure)\b|\bdbgTrace\w*\b", "unsafe"),
        ),
    ),
    Language(
        "racket",
        (".rkt", ".rktl", ".scrbl"),
        LISP,
        (_racket,),
        effects=(
            (r"\((?:display|displayln|print|println|printf|write|writeln|read|read-line)\b", "console"),
            (r"\((?:open-input-file|open-output-file|file->string|file->lines|call-with-input-file|call-with-output-file|with-output-to-file|delete-file|make-directory)\b", "files"),
            (r"\((?:current-seconds|current-inexact-milliseconds|current-milliseconds|current-date|sleep)\b", "clock"),
            (r"\((?:random|random-seed)\b", "randomness"),
            (r"\((?:system|system\*|process|getenv|putenv|exit)\b", "process"),
            (r"\((?:set!|set-box!|hash-set!|vector-set!)\s", "mutation"),
            (r"\((?:thread|place|future)\b", "thread"),
        ),
        impure=("racket/file", "racket/port", "racket/system", "racket/tcp", "racket/udp", "racket/random", "racket/async-channel", "racket/place", "racket/future", "racket/gui", "net", "db", "ffi", "web-server"),
    ),
    Language(
        "fortran",
        (".f90", ".f95", ".f03", ".f08", ".f", ".for", ".F90", ".F"),
        Syntax(line=("!",), block=(), quotes="\"'"),
        (
            namespaces(
                r"(?i)^\s*module\s+(?!procedure\b)(\w+)[ \t]*$",
                r"(?i)^\s*use\s*(?:,\s*(?:non_)?intrinsic\s*)?(?:::)?\s*(?P<spec>\w+)",
                members=False,
                fold=True,
            ),
            paths(r"(?i)^\s*include\s+(?P<q>[\"'])", roots=("", "include"), loose=False, externals=False),
        ),
        effects=(
            (r"(?i)^\s*(?:print\s*[*'\"(]|write\s*\(|read\s*[*(]|open\s*\(|close\s*\(|inquire\s*\()", "input/output"),
            (r"(?i)\bcall\s+(?:random_number|random_seed)\b", "randomness"),
            (r"(?i)\bcall\s+(?:system_clock|cpu_time|date_and_time)\b", "clock"),
            (r"(?i)\bcall\s+(?:get_command_argument|get_environment_variable|execute_command_line|system|exit)\b", "environment"),
            (r"(?i)^\s*common\s*/", "common block"),
        ),
        impure=("mpi", "mpi_f08", "omp_lib", "ifport"),
    ),
    Language(
        "nix",
        (".nix",),
        Syntax(line=("#",), block=(("/*", "*/"), ("''", "''")), quotes='"', multiline='"'),
        (_path_literals(r"(?<![\w./+\-$}\"'<])(\.\.?(?:/[\w.+\-]+)+)", (), ("default.nix",)),),
        effects=(
            (r"\bbuiltins\s*\.\s*getEnv\b", "builtins.getEnv"),
            (r"\bbuiltins\s*\.\s*currentTime\b", "builtins.currentTime"),
            (r"\bbuiltins\s*\.\s*currentSystem\b", "builtins.currentSystem"),
            (r"<\w[\w./+\-]*>", "NIX_PATH"),
        ),
    ),
    Language(
        "shell",
        (".sh", ".bash", ".zsh", ".ksh"),
        HASH,
        (_sourced((r"(?:^|[;&|({]|\bthen\b|\bdo\b|\belse\b)[ \t]*(?:source|\.)[ \t]+(?=\S)",), (".sh",), False),),
        shebang=r"\b(?:ba|z|k|da)?sh\b",
    ),
    Language(
        "powershell",
        (".ps1", ".psm1"),
        Syntax(line=("#",), block=(("<#", "#>"),), quotes="\"'", multiline="\"'", spaced=True),
        (
            _sourced((r"(?:^|[;{(])[ \t]*\.[ \t]+(?=\S)",), (".ps1", ".psm1"), False),
            _sourced((r"(?i)\b(?:Import-Module|using\s+module)[ \t]+(?:-Name[ \t]+)?(?=\S)",), (".psm1", ".ps1", ".psd1"), True),
        ),
    ),
    Language(
        "protobuf",
        (".proto",),
        C,
        (
            paths(
                r"^\s*import\s+(?:public\s+|weak\s+)?(?P<q>\")",
                relative="last",
                roots=("", "proto", "protos", "src", "api"),
                manifests=("buf.yaml",),
            ),
        ),
    ),
    Language(
        "graphql",
        (".graphql", ".gql"),
        Syntax(line=(), block=(), quotes="\"'", triple=True),
        (paths(r"^\s*#\s*import\s+(?:[^\"'\n]*\bfrom\s+)?(?P<q>[\"'])", extensions=(".graphql", ".gql"), loose=False, externals=False),),
    ),
    Language(
        "solidity",
        (".sol",),
        C,
        (
            paths(
                r"^\s*import\s+(?:[^;\"'\n]*?\bfrom\s+)?(?P<q>[\"'])",
                relative="dot",
                roots=("", "src", "contracts"),
                loose=False,
            ),
        ),
        effects=(
            (r"\bblock\s*\.\s*(?:timestamp|number|prevrandao|difficulty|coinbase)\b", "block"),
            (r"\btx\s*\.\s*origin\b", "tx.origin"),
            (r"\.\s*(?:call|delegatecall|staticcall)\s*[({]|\.\s*(?:transfer|send)\s*\(|\bselfdestruct\s*\(", "external call"),
        ),
    ),
    Language(
        "terraform",
        (".tf", ".tofu", ".hcl"),
        Syntax(line=("#", "//"), quotes='"'),
        (_terraform,),
    ),
    Language(
        "qml",
        (".qml",),
        C,
        (_qml,),
        effects=(
            (r"\bXMLHttpRequest\b|\bfetch\s*\(", "network"),
            (r"\bDate\s*\.\s*now\s*\(|\bnew\s+Date\s*\(\s*\)", "clock"),
            (r"\bMath\s*\.\s*random\s*\(", "randomness"),
            (r"\bconsole\s*\.\s*\w+\s*\(", "console"),
            (r"\bQt\s*\.\s*(?:openUrlExternally|quit|exit)\s*\(", "process"),
        ),
        impure=("QtNetwork", "QtWebSockets", "QtWebEngine", "QtQuick.LocalStorage", "Qt.labs.settings", "Qt.labs.platform", "QtCore", "QtPositioning", "QtSensors"),
    ),
    Language(
        "typst",
        (".typ",),
        Syntax(nested=True, quotes='"'),
        (
            paths(
                r"#(?:import|include)\s+(?P<q>\")",
                loose=False,
                is_path=lambda spec: not spec.startswith("@"),
                package=lambda spec: spec.split(":")[0],
            ),
        ),
    ),
    Language(
        "latex",
        (".tex", ".sty", ".cls", ".ltx"),
        Syntax(line=("%",), block=(), quotes=""),
        (
            paths(r"\\(?:input|include|subfile|subfileinclude)\s*\{(?P<spec>[^}\n]+)\}", extensions=(".tex",), loose=False, externals=False),
            paths(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{(?P<spec>[^}\n]+)\}", extensions=(".sty",), split=_commas, loose=False),
            paths(r"\\(?:documentclass|LoadClass)\s*(?:\[[^\]]*\])?\s*\{(?P<spec>[^}\n]+)\}", extensions=(".cls",), loose=False),
            paths(r"\\(?:addbibresource|bibliography)\s*\{(?P<spec>[^}\n]+)\}", extensions=(".bib",), split=_commas, loose=False, externals=False),
        ),
        prepare=lambda text: text.replace("\\%", "  "),
    ),
    Language(
        "cue",
        (".cue",),
        Syntax(block=(), quotes="\"'", triple=True),
        (_cue,),
    ),
    Language(
        "dhall",
        (".dhall",),
        Syntax(line=("--",), block=(("{-", "-}"), ("''", "''")), nested=True, quotes='"'),
        (
            _path_literals(r"(?<![\w./\-])(\.\.?(?:/[\w.\-]+)+)", (".dhall",), ()),
            uses(r"\bhttps?://([\w.\-]+)"),
        ),
        effects=((r"\benv:\w+", "environment"),),
    ),
    Language(
        "nickel",
        (".ncl",),
        Syntax(line=("#",), block=(), quotes='"'),
        (paths(r"\bimport\s+(?P<q>\")", loose=False, externals=False),),
    ),
    Language(
        "rego",
        (".rego",),
        Syntax(line=("#",), block=(), quotes='"`', multiline="`"),
        (
            namespaces(
                r"^package\s+([\w.]+)",
                r"^import\s+(?P<spec>[\w.]+)",
                drop=("data.",),
                qualified=r"\bdata\.([\w.]+)",
            ),
        ),
        effects=(
            (r"\bhttp\s*\.\s*send\s*\(", "http.send"),
            (r"\btime\s*\.\s*now_ns\s*\(", "time.now_ns"),
            (r"\brand\s*\.\s*intn\s*\(", "rand.intn"),
            (r"\bopa\s*\.\s*runtime\s*\(", "opa.runtime"),
            (r"\bnet\s*\.\s*lookup_ip_addr\s*\(", "net.lookup_ip_addr"),
            (r"\buuid\s*\.\s*rfc4122\s*\(", "uuid.rfc4122"),
        ),
    ),
    Language(
        "prolog",
        (".pl", ".pro", ".prolog"),
        Syntax(line=("%",), quotes="\"'"),
        (
            paths(
                r"^:-\s*(?:use_module|ensure_loaded|consult|include|reexport|load_files)\(\s*(?:(?P<q>')|(?P<spec>[a-z][\w/]*)\s*[,)])",
                extensions=(".pl", ".pro", ".prolog"),
                loose=False,
                externals=False,
            ),
            paths(
                r"^:-\s*\[(?P<spec>[^\]\n]+)\]\s*\.",
                extensions=(".pl", ".pro", ".prolog"),
                split=lambda spec: [item.strip().strip("'") for item in spec.split(",")],
                loose=False,
                externals=False,
            ),
            uses(r"^:-\s*(?:use_module|ensure_loaded|reexport)\(\s*library\(\s*([\w/]+)"),
        ),
        effects=(
            (r"\b(?:assert[az]?|retract(?:all)?)\s*\(", "assert"),
            (r"\b(?:nb_setval|b_setval)\s*\(", "global"),
            (r"\b(?:format|write|writeln|print|read|read_term)\s*\(", "console"),
            (r"\b(?:open|see|tell)\s*\(", "files"),
            (r"\b(?:random|random_between|random_member)\s*\(", "randomness"),
            (r"\bget_time\s*\(", "clock"),
            (r"\bshell\s*\(|\bhalt\b", "process"),
        ),
        accepts=_is_prolog,
    ),
    Language(
        "verilog",
        (".sv", ".svh", ".v", ".vh"),
        C,
        (
            paths(r"`include\s+(?P<q>\")", roots=("", "include", "rtl", "src"), loose=False, externals=False),
            namespaces(r"^\s*package\s+(\w+)\s*;", members=False, qualified=r"\b(\w+)::[\w*]", externals=False),
            _verilog_instances,
        ),
        accepts=_is_verilog,
    ),
    Language(
        "vhdl",
        (".vhd", ".vhdl"),
        Syntax(line=("--",), block=(("/*", "*/"),), quotes='"'),
        (
            namespaces(
                r"(?i)^\s*(?:package|entity)\s+(\w+)\s+is\b",
                r"(?i)\b(?:use|entity)\s+(?P<spec>work\.\w+)",
                fold=True,
                drop=("work.",),
                qualified=r"(?i):\s*(?:component\s+)?(\w+)\s+(?:generic|port)\s+map\b",
                externals=False,
            ),
            uses(r"(?i)^\s*use\s+(?!work\.)(\w+)\.(\w+)"),
        ),
    ),
    Language(
        "assembly",
        (".asm", ".s", ".S", ".nasm", ".inc"),
        Syntax(line=(";",), quotes="\"'"),
        (
            paths(
                r"(?i)^\s*[%.#]?include\s+(?P<q>[\"'])",
                r"(?i)^\s*[%.]?include\s+<?(?P<spec>[\w./\-]+)>?",
                roots=("", "include"),
                loose=False,
            ),
        ),
    ),
)

BY_NAME = {language.name: language for language in LANGUAGES}

# rules.py finds a language's lists by its name.
for _language in LANGUAGES:
    effects.DEFAULTS[_language.name] = _language.impure
    effects.ALLOWED[_language.name] = _language.allowed
