"""Finding files and matching them against the globs in architecture.toml."""

import os
import re
import subprocess
from functools import lru_cache

# Build output and vendored code. Hidden directories are skipped as well.
SKIP_DIRS = frozenset(
    {
        "node_modules",
        "target",
        "result",
        "build",
        "dist",
        "_build",
        "vendor",
        "__pycache__",
        "deps",
        "venv",
        "site-packages",
        "bower_components",
        "elm-stuff",
        "nimcache",
        "zig-out",
        "Pods",
    }
)


@lru_cache(maxsize=None)
def _regex(pattern: str) -> re.Pattern[str]:
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("".join(out))


def glob_match(pattern: str, path: str) -> bool:
    """True when path, or a directory above it, matches pattern.

    "src/shell" and "src/shell/**" both match everything below src/shell;
    "*" stays inside one path segment and "**" crosses segments. "." is the
    whole repository.
    """
    pattern = pattern.removeprefix("./").strip("/")
    if pattern in ("", "."):
        return True
    regex = _regex(pattern)
    if regex.fullmatch(path):
        return True
    parent = path
    while "/" in parent:
        parent = parent.rsplit("/", 1)[0]
        if regex.fullmatch(parent):
            return True
    return False


def any_match(patterns: list[str], path: str) -> bool:
    return any(glob_match(p, path) for p in patterns)


def _git_files(root: str) -> list[str] | None:
    """The files git tracks or would add, or None when root is not in a work tree."""
    try:
        result = subprocess.run(
            ["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return [path for path in result.stdout.decode("utf-8", "surrogateescape").split("\0") if path]


def walk(root: str, exclude: list[str], hidden: bool = False) -> list[str]:
    """Every file below root as a sorted, repository-relative posix path.

    In a git work tree that is what git tracks or would add, so what
    .gitignore leaves out is left out here. Build output, vendored code and
    hidden directories are skipped either way. With hidden, the hidden
    directories git lists are kept: that is where .github/workflows is.
    """
    listed = _git_files(root)
    if listed is not None:
        found = []
        for path in listed:
            parts = path.split("/")
            if any((part.startswith(".") and not hidden) or part in SKIP_DIRS for part in parts[:-1]):
                continue
            if any_match(exclude, path) or not os.path.isfile(os.path.join(root, path)):
                continue
            found.append(path)
        return sorted(found)
    found = []
    for directory, subdirs, names in os.walk(root):
        rel_dir = os.path.relpath(directory, root).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir + "/"
        subdirs[:] = sorted(
            d
            for d in subdirs
            if not d.startswith(".")
            and d not in SKIP_DIRS
            and not any_match(exclude, rel_dir + d)
        )
        for name in names:
            path = rel_dir + name
            if not any_match(exclude, path):
                found.append(path)
    return sorted(found)


def read(root: str, path: str) -> str:
    with open(os.path.join(root, path), encoding="utf-8", errors="replace") as handle:
        return handle.read()
