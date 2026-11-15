"""Rules that may only get stricter.

`architecture --since REVISION` compares architecture.toml with what it was at that
revision. Emptying the baseline by loosening the rules is the easy way out:
drop `pure`, widen `may_use`, exclude the file, or move it to a layer that
allows more. Each of those is reported here.
"""

from .config import Config


def weaker(old: Config, new: Config, files: list[str]) -> list[str]:
    """What the rules allow now that they did not allow before, one line each."""
    found = []
    if old.strict and not new.strict:
        found.append("strict was turned off")
    if old.include_tests and not new.include_tests:
        found.append("include_tests was turned off")
    for entry in sorted(set(new.exclude) - set(old.exclude)):
        found.append(f"exclude gained '{entry}'")
    for entry in sorted(set(new.purity_allow) - set(old.purity_allow)):
        found.append(f"[purity] allow gained '{entry}'")
    for entry in sorted(set(old.purity_forbid) - set(new.purity_forbid)):
        found.append(f"[purity] forbid lost '{entry}'")
    # Where imports are resolved from: without a root an import stops leading to a file of the
    # repository, and the use it stood for is no longer seen.
    for name, before, after in (
        ("[sources] roots", old.roots, new.roots),
        ("[python] roots", old.python_roots, new.python_roots),
        ("[cpp] include_dirs", old.cpp_include_dirs, new.cpp_include_dirs),
        ("[javascript] aliases", sorted(old.js_aliases), sorted(new.js_aliases)),
    ):
        for entry in sorted(set(before) - set(after)):
            found.append(f"{name} lost '{entry}'")

    now = {layer.name: layer for layer in new.layers}
    for layer in old.layers:
        same = now.get(layer.name)
        if same is None:
            continue  # renamed or split: what happened to its files is checked below
        if layer.pure and not same.pure:
            found.append(f"layer '{layer.name}' is no longer pure")
        if layer.apart and not same.apart:
            found.append(f"layer '{layer.name}' no longer keeps its parts apart")
        for used in sorted(set(same.may_use) - set(layer.may_use)):
            found.append(f"layer '{layer.name}' may now use '{used}'")
        for entry in sorted(set(layer.forbid_external) - set(same.forbid_external)):
            found.append(f"layer '{layer.name}' no longer forbids '{entry}'")

    # The same file under the old rules and the new: did it land somewhere that asks less of it?
    for path in files:
        before, after = old.layer_of(path), new.layer_of(path)
        if before is None:
            continue
        if after is None:
            found.append(f"{path} was in '{before.name}' and is in no layer now")
        elif before.pure and not after.pure:
            found.append(f"{path} left the pure layer '{before.name}' for '{after.name}'")
    return found
