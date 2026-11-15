"""What archcheck prints. The text is written for whoever has to fix it, person or agent."""

import json

from .baseline import Key
from .model import Violation


def text(new: list[Violation], known: int, fixed: list[Key], grown: list[Key], checked: int, placed: int) -> str:
    out = []
    for violation in new:
        times = f" ({violation.count} times in this file)" if violation.count > 1 else ""
        out.append(f"{violation.file}:{violation.line}: {violation.rule}: {violation.message}{times}")
        out.append(f"    fix: {violation.fix}")
    if fixed:
        out.append("")
        out.append(f"{len(fixed)} baseline entries no longer occur:")
        out.extend(f"    {rule}: {file} -> {target}" for rule, file, target in fixed)
        out.append("    Run `archcheck --prune` and commit the shorter baseline.")
    if grown:
        out.append("")
        out.append(f"{len(grown)} entries were added to the baseline; it may only get shorter:")
        out.extend(f"    {rule}: {file} -> {target}" for rule, file, target in grown)
        out.append("    Fix these violations and take them off the baseline again.")
    summary = f"{checked} files checked, {placed} of them in a layer, {known} known violations in the baseline"
    if new or fixed or grown:
        out.append("")
        reasons = [f"{len(new)} new violations"]
        if fixed:
            reasons.append(f"{len(fixed)} baseline entries to remove")
        if grown:
            reasons.append(f"{len(grown)} entries added to the baseline")
        out.append(f"archcheck: FAIL: {', '.join(reasons)} ({summary})")
    else:
        out.append(f"archcheck: ok ({summary})")
    return "\n".join(out)


def as_json(new: list[Violation], known: list[Violation], fixed: list[Key], grown: list[Key], warnings: list[str]) -> str:
    def row(violation: Violation) -> dict:
        return {
            "rule": violation.rule,
            "file": violation.file,
            "line": violation.line,
            "target": violation.target,
            "message": violation.message,
            "fix": violation.fix,
            "count": violation.count,
        }

    def key(item: Key) -> dict:
        return {"rule": item[0], "file": item[1], "target": item[2]}

    return json.dumps(
        {
            "ok": not (new or fixed or grown),
            "new": [row(v) for v in new],
            "known": [row(v) for v in known],
            "fixed": [key(k) for k in fixed],
            "grown": [key(k) for k in grown],
            "warnings": warnings,
        },
        indent=2,
        ensure_ascii=False,
    )
