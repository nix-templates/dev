"""Turning references into violations of the layers in architecture.toml."""

from .config import Config, Layer
from .effects import ALLOWED, DEFAULTS, first_covering, language_of
from .model import Ref, Scan, Violation


def _may_use(layer: Layer) -> str:
    return ", ".join(f"'{name}'" for name in layer.may_use) or "no other layer"


def _with_hint(text: str, layer: Layer) -> str:
    return f"{text} {layer.hint}" if layer.hint else text


def _layer_violation(ref: Ref, source: Layer, target: Layer) -> Violation:
    return Violation(
        rule="layer",
        file=ref.file,
        line=ref.line,
        target=ref.target,
        message=f"'{source.name}' may not use '{target.name}': {ref.path} is {ref.target}",
        fix=_with_hint(
            f"'{source.name}' may use {_may_use(source)}. Move what both need into a layer '{source.name}' may use, "
            f"or define the interface in '{source.name}' and implement it in '{target.name}'. "
            "Do not add this to the baseline.",
            source,
        ),
    )


def _apart_violation(ref: Ref, layer: Layer, own: str, other: str) -> Violation:
    return Violation(
        rule="layer",
        file=ref.file,
        line=ref.line,
        target=ref.target,
        message=f"'{layer.name}' keeps its parts apart: '{own}' may not use '{other}' ({ref.path} is {ref.target})",
        fix=_with_hint(
            f"Each entry under paths of '{layer.name}' stands on its own. Move what both need into a layer "
            f"'{layer.name}' may use ({_may_use(layer)}). Do not add this to the baseline.",
            layer,
        ),
    )


def _tests_violation(ref: Ref, source: Layer) -> Violation:
    return Violation(
        rule="layer",
        file=ref.file,
        line=ref.line,
        target=ref.target,
        message=f"'{source.name}' may not use test code: {ref.path} is {ref.target}",
        fix=_with_hint(
            f"Code that ships does not depend on its tests. Move what both need out of the tests, "
            f"into a layer '{source.name}' may use. Do not add this to the baseline.",
            source,
        ),
    )


def _purity_violation(ref: Ref, layer: Layer, what: str) -> Violation:
    return Violation(
        rule="purity",
        file=ref.file,
        line=ref.line,
        target=what,
        message=f"'{layer.name}' is a pure layer and may not use {what} ({ref.path})",
        fix=_with_hint(
            "Pure code gives the same output for the same input and changes nothing outside itself. "
            "Take the value as an argument, or return a description of what must happen, "
            "and do the work in a layer that is not pure. Do not add this to the baseline.",
            layer,
        ),
    )


def _external_violation(ref: Ref, layer: Layer, entry: str) -> Violation:
    return Violation(
        rule="external",
        file=ref.file,
        line=ref.line,
        target=entry,
        message=f"'{layer.name}' may not depend on {entry} ({ref.path})",
        fix=_with_hint(
            f"Keep {entry} in a layer that is allowed to use it, behind an interface that '{layer.name}' owns. "
            "Do not add this to the baseline.",
            layer,
        ),
    )


def _check(ref: Ref, config: Config, scan: Scan) -> Violation | None:
    source = config.layer_of(ref.file)
    if source is None:
        return None
    languages = scan.language
    if ref.kind == "internal":
        target = config.layer_of(ref.target)
        if target is None:
            # Test files are in no layer unless the rules give them one, and nothing may use them.
            return _tests_violation(ref, source) if ref.target in scan.tests else None
        if target is source:
            if source.apart:
                own, other = source.part_of(ref.file), source.part_of(ref.target)
                if own != other:
                    return _apart_violation(ref, source, own or "?", other or "?")
            return None
        if target.name in source.may_use:
            return None
        return _layer_violation(ref, source, target)
    if ref.kind == "effect":
        if source.pure and ref.target not in config.purity_allow:
            return _purity_violation(ref, source, ref.target)
        return None
    entry = first_covering(source.forbid_external, ref.target, ref.path)
    if entry:
        return _external_violation(ref, source, entry)
    if source.pure:
        language = languages.get(ref.file) or language_of(ref.file)
        allowed = tuple(config.purity_allow) + ALLOWED.get(language, ())
        if first_covering(allowed, ref.target, ref.path):
            return None
        entry = first_covering(tuple(config.purity_forbid) + DEFAULTS.get(language, ()), ref.target, ref.path)
        if entry:
            return _purity_violation(ref, source, entry)
    return None


def evaluate(config: Config, scan: Scan) -> list[Violation]:
    """Every violation once per (rule, file, target), with the first line and a count."""
    found: dict[tuple[str, str, str], Violation] = {}
    for ref in sorted(scan.refs, key=lambda r: (r.file, r.line)):
        violation = _check(ref, config, scan)
        if violation is None:
            continue
        earlier = found.get(violation.key)
        if earlier is None:
            found[violation.key] = violation
        else:
            found[violation.key] = Violation(**{**earlier.__dict__, "count": earlier.count + 1})
    for path, reason in scan.unreadable:
        if config.layer_of(path) is None:
            scan.warnings.append(f"{path}: could not be parsed, and it is in no layer, so it was skipped ({reason})")
            continue
        violation = Violation(
            rule="unreadable",
            file=path,
            line=1,
            target="-",
            message=f"could not be parsed, so its rules were not checked ({reason})",
            fix="Fix the syntax error. If this file is not source code, list it under exclude in architecture.toml.",
        )
        found[violation.key] = violation
    if config.strict:
        for path in scan.files:
            if config.layer_of(path) is None:
                violation = Violation(
                    rule="unassigned",
                    file=path,
                    line=1,
                    target="-",
                    message="this file is in no layer",
                    fix="Add it to the paths of a layer in architecture.toml, or move it to where its layer lives.",
                )
                found[violation.key] = violation
    return sorted(found.values(), key=lambda v: (v.file, v.line, v.rule, v.target))
