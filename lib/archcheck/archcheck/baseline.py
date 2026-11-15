"""The baseline: violations that existed when a repository adopted its rules.

It is a list that may only get shorter. A violation in it does not fail the
check; one that is not in it does, and so does an entry that no longer occurs,
so the change that fixes a violation also takes it off the list.
"""

import json
import os
import subprocess

Key = tuple[str, str, str]


class BaselineError(Exception):
    pass


def parse(text: str) -> set[Key]:
    try:
        data = json.loads(text)
        return {(item["rule"], item["file"], item["target"]) for item in data["violations"]}
    except (ValueError, KeyError, TypeError) as error:
        raise BaselineError(f"the baseline is not in the format archcheck writes: {error}") from error


def load(path: str) -> set[Key]:
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as handle:
        return parse(handle.read())


def dump(keys: set[Key]) -> str:
    """One violation per line, sorted, so a diff shows exactly what changed."""
    lines = [
        "  " + json.dumps({"rule": rule, "file": file, "target": target}, ensure_ascii=False)
        for rule, file, target in sorted(keys, key=lambda k: (k[1], k[0], k[2]))
    ]
    body = ",\n".join(lines)
    return '{\n "version": 1,\n "violations": [\n' + body + ("\n" if lines else "") + " ]\n}\n"


def save(path: str, keys: set[Key]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(dump(keys))


def at_revision(root: str, revision: str, config_name: str, baseline_name: str) -> set[Key] | None:
    """The baseline as it was at a git revision; None when the rules did not exist there yet."""

    def show(name: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", root, "show", f"{revision}:./{name}"], capture_output=True, text=True, check=False
        )
        return result.stdout if result.returncode == 0 else None

    known = subprocess.run(
        ["git", "-C", root, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    if known.returncode != 0:
        raise BaselineError(f"git does not know the revision '{revision}'")
    if show(config_name) is None:
        return None
    text = show(baseline_name)
    return parse(text) if text is not None else set()
