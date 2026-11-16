"""JavaScript and TypeScript: import, export-from, require() and import() specifiers.

Read from the text with comments removed, so it is close but not exact:
specifiers built at run time and paths mapped in tsconfig.json are not
followed. Map those with [javascript] aliases in architecture.toml.
"""

import posixpath
import re

from .model import Ref, Scan
from .walk import read

EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte")

_SPECIFIER = re.compile(
    r"""(?:\bimport\s+(?:type\s+)?(?:[\w*${}\s,]+\s+from\s+)?   # import x from, import {a} from, import "x"
         |\bexport\s+(?:type\s+)?(?:\*(?:\s+as\s+\w+)?|\{[^}]*\})\s+from\s+
         |\brequire\s*\(\s*
         |\bimport\s*\(\s*)
        (['"])([^'"\n]+)\1""",
    re.VERBOSE,
)

_EFFECTS = (
    (re.compile(r"\bfetch\s*\("), "fetch()"),
    (re.compile(r"\bDate\s*\.\s*now\s*\("), "Date.now()"),
    (re.compile(r"\bnew\s+Date\s*\(\s*\)"), "new Date()"),
    (re.compile(r"\bMath\s*\.\s*random\s*\("), "Math.random()"),
    (re.compile(r"\bconsole\s*\.\s*\w+\s*\("), "console"),
    (re.compile(r"\b(?:document|window|navigator)\s*\."), "DOM"),
    (re.compile(r"\b(?:localStorage|sessionStorage|indexedDB)\b"), "browser storage"),
    (re.compile(r"\b(?:setTimeout|setInterval|requestAnimationFrame)\s*\("), "timer"),
    (re.compile(r"\bXMLHttpRequest\b|\bnew\s+WebSocket\b"), "network"),
    (re.compile(r"\bprocess\s*\.\s*(?:env|argv|exit|stdout|stderr|stdin|cwd)\b"), "process"),
)


def strip_comments(src: str) -> str:
    """Blank out // and /* */ comments; strings and template literals stay as written."""
    out = list(src)
    n = len(src)
    i = 0
    while i < n:
        c = src[i]
        if c in "'\"`":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\n" and c != "`":
                    break
                j += 2 if src[j] == "\\" else 1
            i = j + 1
        elif src.startswith("//", i):
            end = src.find("\n", i)
            end = n if end < 0 else end
            out[i:end] = " " * (end - i)
            i = end
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            end = n if end < 0 else end + 2
            for k in range(i, end):
                if out[k] != "\n":
                    out[k] = " "
            i = end
        else:
            i += 1
    return "".join(out)



def component_code(text: str, svelte: bool = False) -> tuple[str, list[tuple[str, int]]]:
    """Script blocks and brace expressions, preserving original line positions.

    This is text analysis, not a Vue/Svelte compiler. Template directives and
    generated framework imports are outside its view, as are generated imports
    in other languages' build systems.
    """
    blank = lambda value: "".join("\n" if char == "\n" else " " for char in value)
    clean = re.sub(r"<!--.*?-->", lambda match: blank(match[0]), text, flags=re.DOTALL)
    code = list(blank(clean))
    external = []
    scripts = list(re.finditer(r"<script\b([^>]*)>(.*?)</script\s*>", clean, re.DOTALL | re.IGNORECASE))
    if len(scripts) != len(re.findall(r"<script\b", clean, re.IGNORECASE)):
        raise ValueError("component has an unclosed script block")
    hidden = list(clean)
    for match in scripts:
        start, end = match.span(2)
        code[start:end] = clean[start:end]
        attributes = match[1]
        source = re.search(r"\bsrc\s*=\s*(['\"])(.*?)\1", attributes, re.DOTALL)
        if source:
            external.append((source[2], match.start(1) + source.start()))
        start, end = match.span()
        hidden[start:end] = blank(clean[start:end])
    # CSS braces are not JavaScript expressions.
    markup = re.sub(r"<style\b[^>]*>.*?</style\s*>", lambda match: blank(match[0]), "".join(hidden), flags=re.DOTALL | re.IGNORECASE)
    index = 0
    while index < len(markup):
        if (svelte and markup[index] != "{") or (not svelte and not markup.startswith("{{", index)):
            index += 1
            continue
        start = index
        depth = 1 if svelte else 2
        index += depth
        while index < len(markup) and depth:
            char = markup[index]
            if markup.startswith("/*", index):
                end = markup.find("*/", index + 2)
                if end < 0:
                    raise ValueError("component has an unclosed JavaScript comment")
                index = end + 2
                continue
            if markup.startswith("//", index):
                end = markup.find("\n", index + 2)
                index = len(markup) if end < 0 else end
                continue
            if char in "'\"`":
                quote = char
                index += 1
                while index < len(markup) and markup[index] != quote:
                    index += 2 if markup[index] == "\\" else 1
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1
        if depth:
            raise ValueError("component has an unclosed template expression")
        code[start:index] = markup[start:index]
    return "".join(code), external


def is_test(path: str) -> bool:
    parts = path.split("/")
    return bool({"__tests__", "tests", "test", "e2e"} & set(parts[:-1])) or bool(
        re.search(r"\.(test|spec)\.(?:[cm]?[jt]sx?|vue|svelte)$", parts[-1])
    )


def _find(candidate: str, known: set[str]) -> str | None:
    if candidate in known:
        return candidate
    # TypeScript sources import "./x.js" for what is x.ts on disk.
    stem = re.sub(r"\.[cm]?jsx?$", "", candidate)
    for base in (candidate, stem):
        for extension in EXTENSIONS:
            if base + extension in known:
                return base + extension
        for extension in EXTENSIONS:
            if f"{base}/index{extension}" in known:
                return f"{base}/index{extension}"
    return None


def package_of(specifier: str) -> str:
    specifier = specifier.removeprefix("node:")
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") and len(parts) > 1 else parts[0]


def translation(path: str, text: str) -> bool:
    """A Qt translation file: it ends in .ts as well, and is XML."""
    return path.endswith(".ts") and text.lstrip().startswith(("<?xml", "<!DOCTYPE TS"))


def extract(root: str, files: list[str], aliases: dict[str, str], include_tests: bool, scan: Scan) -> None:
    sources = [p for p in files if p.endswith(EXTENSIONS) and not p.endswith(".d.ts")]
    known = set(sources)
    for path in sources:
        if not include_tests and is_test(path):
            scan.tests.add(path)
            continue
        text = read(root, path)
        if translation(path, text):
            continue
        scan.files.append(path)
        external = []
        if path.endswith((".vue", ".svelte")):
            try:
                text, external = component_code(text, svelte=path.endswith(".svelte"))
            except ValueError as error:
                scan.unreadable.append((path, str(error)))
                continue
        code = strip_comments(text)
        directory = posixpath.dirname(path)
        specifiers = [(match.group(2), match.start()) for match in _SPECIFIER.finditer(code)] + external
        for specifier, position in specifiers:
            line = code.count("\n", 0, position) + 1
            candidate = None
            if specifier.startswith("."):
                candidate = posixpath.normpath(posixpath.join(directory, specifier))
            else:
                for prefix, target in aliases.items():
                    if specifier.startswith(prefix):
                        candidate = posixpath.normpath(posixpath.join(target, specifier[len(prefix) :]))
                        break
            if candidate is not None:
                found = _find(candidate, known)
                if found and found != path:
                    scan.refs.append(Ref(path, line, "internal", found, specifier))
            else:
                bare = specifier.removeprefix("node:")
                scan.refs.append(Ref(path, line, "external", package_of(specifier), bare))
        for pattern, name in _EFFECTS:
            for match in pattern.finditer(code):
                scan.refs.append(Ref(path, code.count("\n", 0, match.start()) + 1, "effect", name, name))
