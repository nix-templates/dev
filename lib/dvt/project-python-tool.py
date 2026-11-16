"""Execute an existing console entry point in the selected project interpreter."""
import importlib.metadata
import sys

name, *arguments = sys.argv[1:]
entries = tuple(importlib.metadata.entry_points(group='console_scripts', name=name))
if len(entries) != 1:
    sys.exit(f'project tool {name!r} is missing or ambiguous in this interpreter; no dependency was installed')
sys.argv = [name, *arguments]
sys.exit(entries[0].load()())
