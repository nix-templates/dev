"""The arch command.

With no arguments it prints the machine's hardware name, exactly as the `arch`
of GNU coreutils does, so a script that calls `arch` still gets what it expects
when this one comes first on PATH. Everything this program adds is behind a flag.
"""

import argparse
import os
import platform
import sys

from . import __version__, baseline, cpp, javascript, python, report, rust
from .config import Config, ConfigError, parse
from .model import Scan
from .rules import evaluate
from .walk import walk

CONFIG = "architecture.toml"
BASELINE = "architecture-baseline.json"


def scan_repository(root: str, config: Config) -> Scan:
    files = walk(root, config.exclude)
    scan = Scan()
    rust.extract(root, files, config.include_tests, scan)
    python.extract(root, files, config.python_roots, config.include_tests, scan)
    javascript.extract(root, files, config.js_aliases, config.include_tests, scan)
    cpp.extract(root, files, config.cpp_include_dirs, config.include_tests, scan)
    return scan


def _explain(config: Config, scan: Scan) -> str:
    out = []
    by_layer: dict[str, list[str]] = {layer.name: [] for layer in config.layers}
    unassigned = []
    for path in scan.files:
        layer = config.layer_of(path)
        (by_layer[layer.name] if layer else unassigned).append(path)
    for layer in config.layers:
        uses = ", ".join(layer.may_use) or "nothing"
        out.append(f"{layer.name} ({'pure, ' if layer.pure else ''}may use: {uses}): {len(by_layer[layer.name])} files")
        out.extend(f"    {path}" for path in by_layer[layer.name])
    out.append(f"in no layer: {len(unassigned)} files")
    out.extend(f"    {path}" for path in unassigned)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(platform.machine())
        return 0

    parser = argparse.ArgumentParser(
        prog="arch",
        description="Check the dependency and purity rules in architecture.toml. "
        "With --check it exits 0 when they hold, 1 when they do not and 2 when it could not run. "
        "With no arguments it prints the machine's hardware name, as coreutils' arch does.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="check the rules")
    mode.add_argument("--accept", action="store_true", help="write every current violation to the baseline (for adopting the rules)")
    mode.add_argument("--prune", action="store_true", help="remove baseline entries that no longer occur, then check")
    mode.add_argument("--explain", action="store_true", help="list the layers and the files in each")
    mode.add_argument("--version", action="version", version=f"arch {__version__}")
    parser.add_argument("--root", default=".", help="the repository to check (default: the current directory)")
    parser.add_argument("--config", help=f"the rules (default: {CONFIG} in the root)")
    parser.add_argument("--baseline", help=f"the known violations (default: {BASELINE} in the root)")
    parser.add_argument("--no-baseline", action="store_true", help="report every violation, known or not")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--since", metavar="REVISION", help="also fail when the baseline has entries that REVISION's baseline lacks")
    args = parser.parse_args(argv)

    root = args.root
    config_path = args.config or os.path.join(root, CONFIG)
    baseline_path = args.baseline or os.path.join(root, BASELINE)
    if not os.path.exists(config_path):
        if args.config:
            print(f"arch: {config_path} does not exist", file=sys.stderr)
            return 2
        print(f":: skipping arch (no {CONFIG} here)")
        return 0

    try:
        with open(config_path, encoding="utf-8") as handle:
            config = parse(handle.read())
        scan = scan_repository(root, config)
        violations = evaluate(config, scan)
        known_keys = set() if args.no_baseline else baseline.load(baseline_path)
        previous = None
        if args.since:
            previous = baseline.at_revision(
                root, args.since, os.path.relpath(config_path, root), os.path.relpath(baseline_path, root)
            )
    except (ConfigError, baseline.BaselineError) as error:
        print(f"arch: {error}", file=sys.stderr)
        return 2

    for warning in scan.warnings:
        print(f"arch: warning: {warning}", file=sys.stderr)

    if args.explain:
        print(_explain(config, scan))
        return 0

    current = {violation.key for violation in violations}
    if args.accept:
        baseline.save(baseline_path, current)
        print(f"arch: wrote {len(current)} violations to {baseline_path}")
        return 0

    new = [violation for violation in violations if violation.key not in known_keys]
    known = [violation for violation in violations if violation.key in known_keys]
    fixed = sorted(known_keys - current)
    if args.prune:
        baseline.save(baseline_path, known_keys & current)
        print(f"arch: removed {len(fixed)} entries from {baseline_path}")
        fixed = []
        known_keys &= current
    grown = sorted(known_keys - previous) if previous is not None else []

    if args.format == "json":
        print(report.as_json(new, known, fixed, grown, scan.warnings))
    else:
        placed = sum(1 for path in scan.files if config.layer_of(path) is not None)
        print(report.text(new, len(known), fixed, grown, len(scan.files), placed))
    return 1 if (new or fixed or grown) else 0
