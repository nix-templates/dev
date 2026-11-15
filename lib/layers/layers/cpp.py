"""C and C++: #include lines. Quoted includes that resolve to a file in the repository are internal."""

import posixpath
import re

from .model import Ref, Scan
from .walk import read

EXTENSIONS = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx")

_INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*([<"])([^>"\n]+)[>"]', re.M)


def is_test(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return bool({"tests", "test"} & set(parts[:-1])) or name.startswith(("test_", "tst_")) or "_test." in name


def extract(root: str, files: list[str], include_dirs: list[str], include_tests: bool, scan: Scan) -> None:
    sources = [p for p in files if p.endswith(EXTENSIONS)]
    known = set(sources)
    search = [d.strip("/") for d in include_dirs] + [""]
    for path in sources:
        if not include_tests and is_test(path):
            scan.tests.add(path)
            continue
        scan.files.append(path)
        text = read(root, path)
        directory = posixpath.dirname(path)
        for match in _INCLUDE.finditer(text):
            quoted, header = match.group(1) == '"', match.group(2).strip()
            line = text.count("\n", 0, match.start()) + 1
            found = None
            if quoted:
                for base in [directory] + search:
                    candidate = posixpath.normpath(posixpath.join(base, header)) if base else posixpath.normpath(header)
                    if candidate in known:
                        found = candidate
                        break
            if found:
                if found != path:
                    scan.refs.append(Ref(path, line, "internal", found, header))
            else:
                scan.refs.append(Ref(path, line, "external", header.split("/")[0], header))
