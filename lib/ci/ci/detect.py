"""Which of the library's languages a checkout is written in.

Nothing here knows a file type of its own. A file belongs to the language
`architecture` reads it as, and the MCP server's READ_AS says which language of
the library that is. A language that `architecture` has no reader for, or that shares
its files with another, names the files that mark it in its module in
lib/languages (`marks`), and the languages it then stands in for (`insteadOf`).
"""

import fnmatch

import server
from layers import cli
from layers.walk import glob_match, walk


def marked(mark: str, path: str) -> bool:
    """A mark with a slash is a path from the top of the checkout; without one it is a file's name, anywhere."""
    if "/" in mark:
        return glob_match(mark, path)
    return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], mark)


def among(files: list[str], read: dict[str, list[str]], marks: dict[str, dict]) -> dict[str, list[str]]:
    """The languages these files are written in, each with the files that say so.

    read is which reader of `architecture` takes which file (layers.cli.read_by).
    marks has, for every language of the library, its `marks` (None when its
    module names none) and its `insteadOf`.
    """
    found = {}
    for name, entry in marks.items():
        if entry["marks"] is None:
            mine = sorted({path for reader in server.read_as(name) for path in read.get(reader, [])})
        else:
            mine = [path for path in files if any(marked(mark, path) for mark in entry["marks"])]
        if mine:
            found[name] = mine
    replaced = {other for name in found for other in marks[name]["insteadOf"]}
    return {name: found[name] for name in sorted(found) if name not in replaced}


def found(root: str, marks: dict[str, dict]) -> dict[str, list[str]]:
    """The languages of the checkout at root, from the files git lists there."""
    files = walk(root, [], hidden=True)
    return among(files, cli.read_by(root, files), marks)
