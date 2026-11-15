"""The layers command: check a repository against the layers in architecture.toml."""

import argparse
import json
import os
import re
import sys

from . import __version__, baseline, cpp, generic, javascript, python, ratchet, report, rust
from .config import Config, ConfigError, parse
from .languages import LANGUAGES
from .model import Scan
from .rules import evaluate
from .walk import read, walk

PYTHON_SCRIPT = re.compile(r"\bpython[\d.]*\b")
CONFIG = "architecture.toml"
BASELINE = "architecture-baseline.json"


def scan_repository(root: str, config: Config) -> Scan:
    files = walk(root, config.exclude)
    scan = Scan()
    scripts = generic.first_lines(root, files)
    python_scripts = [path for path, first in scripts.items() if PYTHON_SCRIPT.search(first)]
    rust.extract(root, files, config.include_tests, scan)
    python.extract(root, files, config.python_roots + config.roots, config.include_tests, scan, python_scripts)
    javascript.extract(root, files, config.js_aliases, config.include_tests, scan)
    cpp.extract(root, files, config.cpp_include_dirs + config.roots, config.include_tests, scan)
    generic.extract(root, files, LANGUAGES, config, scan, scripts)
    return scan


# The four languages with a reader of their own, then the ones read from text.
OWN = (
    ("rust", (".rs", "Cargo.toml")),
    ("python", (".py", ".ipynb")),
    ("javascript", javascript.EXTENSIONS),
    ("cpp", cpp.EXTENSIONS),
)


def languages() -> list[tuple[str, tuple[str, ...]]]:
    return sorted(list(OWN) + [(language.name, language.extensions) for language in LANGUAGES])


def read_by(root: str, files: list[str]) -> dict[str, list[str]]:
    """The languages of languages() that have files among these, each with its files.

    It tells which reader takes which file, without reading what the files use.
    """
    scripts = generic.first_lines(root, files)
    by_name: dict[str, list[str]] = {}
    for path in files:
        by_name.setdefault(path.rsplit("/", 1)[-1], []).append(path)

    def named(*names: str) -> list[str]:
        return [path for name in names for path in by_name.get(name, [])]

    found: dict[str, list[str]] = {}
    for name, endings in OWN:
        suffixes = tuple(ending for ending in endings if ending.startswith("."))
        found[name] = [path for path in files if path.endswith(suffixes)] + named(*(set(endings) - set(suffixes)))
    found["python"] += [path for path, first in scripts.items() if PYTHON_SCRIPT.search(first)]
    found["javascript"] = [path for path in found["javascript"] if not javascript.translation(path, read(root, path))]
    extensions = generic.by_extension(files)
    for language in LANGUAGES:
        found[language.name] = generic.files_of(language, extensions, named, scripts, lambda path: read(root, path))
    return {name: sorted(set(mine)) for name, mine in found.items() if mine}


def _explain(config: Config, scan: Scan, as_json: bool = False) -> str:
    out = []
    by_layer: dict[str, list[str]] = {layer.name: [] for layer in config.layers}
    unassigned = []
    for path in scan.files:
        layer = config.layer_of(path)
        (by_layer[layer.name] if layer else unassigned).append(path)
    if as_json:
        return json.dumps(
            {
                "layers": [
                    {"name": layer.name, "pure": layer.pure, "may_use": layer.may_use, "files": by_layer[layer.name]}
                    for layer in config.layers
                ],
                "in_no_layer": unassigned,
            },
            indent=2,
            ensure_ascii=False,
        )
    for layer in config.layers:
        uses = ", ".join(layer.may_use) or "nothing"
        kind = ("pure, " if layer.pure else "") + ("parts apart, " if layer.apart else "")
        out.append(f"{layer.name} ({kind}may use: {uses}): {len(by_layer[layer.name])} files")
        out.extend(f"    {path}" for path in by_layer[layer.name])
    out.append(f"in no layer: {len(unassigned)} files")
    out.extend(f"    {path}" for path in unassigned)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    parser = argparse.ArgumentParser(
        prog="layers",
        description="Check the dependency and purity rules in architecture.toml. "
        "It exits 0 when they hold, 1 when they do not and 2 when it could not run.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="check the rules (what happens when no other mode is named)")
    mode.add_argument("--accept", action="store_true", help="write every current violation to the baseline (for adopting the rules)")
    mode.add_argument("--prune", action="store_true", help="remove baseline entries that no longer occur, then check")
    mode.add_argument("--explain", action="store_true", help="list the layers and the files in each")
    mode.add_argument("--languages", action="store_true", help="list the languages this program reads, and their files")
    mode.add_argument("--version", action="version", version=f"layers {__version__}")
    parser.add_argument("--root", default=".", help="the repository to check (default: the current directory)")
    parser.add_argument("--config", help=f"the rules (default: {CONFIG} in the root)")
    parser.add_argument("--baseline", help=f"the known violations (default: {BASELINE} in the root)")
    parser.add_argument("--no-baseline", action="store_true", help="report every violation, known or not")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--since",
        metavar="REVISION",
        help="also fail when the baseline has entries that REVISION's baseline lacks, or the rules allow more than they did there",
    )
    parser.add_argument("--allow-weaker", action="store_true", help="with --since: let rules that got weaker pass, for the change where that was agreed")
    args = parser.parse_args(argv)

    if args.languages:
        for name, extensions in languages():
            print(f"{name}: {' '.join(extensions)}")
        return 0

    root = args.root
    config_path = args.config or os.path.join(root, CONFIG)
    baseline_path = args.baseline or os.path.join(root, BASELINE)
    if not os.path.exists(config_path):
        if args.config:
            print(f"layers: {config_path} does not exist", file=sys.stderr)
            return 2
        print(f":: skipping layers (no {CONFIG} here)")
        return 0

    try:
        with open(config_path, encoding="utf-8") as handle:
            config = parse(handle.read())
        scan = scan_repository(root, config)
        violations = evaluate(config, scan)
        known_keys = set() if args.no_baseline else baseline.load(baseline_path)
        previous = None
        weaker: list[str] = []
        if args.since:
            previous = baseline.at_revision(
                root, args.since, os.path.relpath(config_path, root), os.path.relpath(baseline_path, root)
            )
            before = baseline.file_at(root, args.since, os.path.relpath(config_path, root))
            if before is None:
                # Say so: a run that compared nothing must not look like one that found nothing.
                scan.warnings.append(f"{args.since} has no {CONFIG}, so --since had nothing to compare with")
            elif not args.allow_weaker:
                weaker = ratchet.weaker(parse(before), config, scan.files)
    except (ConfigError, baseline.BaselineError) as error:
        print(f"layers: {error}", file=sys.stderr)
        return 2

    for warning in scan.warnings:
        print(f"layers: warning: {warning}", file=sys.stderr)

    if args.explain:
        print(_explain(config, scan, args.format == "json"))
        return 0

    current = {violation.key for violation in violations}
    if args.accept:
        baseline.save(baseline_path, current)
        print(f"layers: wrote {len(current)} violations to {baseline_path}")
        return 0

    new = [violation for violation in violations if violation.key not in known_keys]
    known = [violation for violation in violations if violation.key in known_keys]
    fixed = sorted(known_keys - current)
    if args.prune:
        baseline.save(baseline_path, known_keys & current)
        print(f"layers: removed {len(fixed)} entries from {baseline_path}")
        fixed = []
        known_keys &= current
    grown = sorted(known_keys - previous) if previous is not None else []

    if args.format == "json":
        print(report.as_json(new, known, fixed, grown, scan.warnings, weaker))
    else:
        placed = sum(1 for path in scan.files if config.layer_of(path) is not None)
        print(report.text(new, len(known), fixed, grown, len(scan.files), placed, weaker))
    return 1 if (new or fixed or grown or weaker) else 0
