"""Reading and checking architecture.toml."""

import tomllib
from dataclasses import dataclass, field

from .walk import glob_match


class ConfigError(Exception):
    pass


@dataclass
class Layer:
    name: str
    paths: list[str]
    may_use: list[str] = field(default_factory=list)
    pure: bool = False
    forbid_external: list[str] = field(default_factory=list)
    hint: str = ""


@dataclass
class Config:
    layers: list[Layer]
    strict: bool = False
    include_tests: bool = False
    exclude: list[str] = field(default_factory=list)
    purity_allow: list[str] = field(default_factory=list)
    purity_forbid: list[str] = field(default_factory=list)
    python_roots: list[str] = field(default_factory=list)
    cpp_include_dirs: list[str] = field(default_factory=list)
    js_aliases: dict[str, str] = field(default_factory=dict)

    def layer_of(self, path: str) -> Layer | None:
        """The first layer, in the order written, whose paths match."""
        for layer in self.layers:
            if any(glob_match(pattern, path) for pattern in layer.paths):
                return layer
        return None


_TOP = {"version", "strict", "include_tests", "exclude", "layer", "purity", "python", "cpp", "javascript"}
_LAYER = {"name", "paths", "may_use", "pure", "forbid_external", "hint"}


def _only(table: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(f"{where}: unknown key {', '.join(unknown)} (allowed: {', '.join(sorted(allowed))})")


def _strings(value, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where}: expected a list of strings")
    return list(value)


def _flag(value, where: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{where}: expected true or false")
    return value


def parse(text: str) -> Config:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"not valid TOML: {error}") from error

    _only(data, _TOP, "architecture.toml")
    if data.get("version", 1) != 1:
        raise ConfigError(f"version {data['version']!r} is not supported; this archcheck reads version 1")

    raw_layers = data.get("layer", [])
    if not isinstance(raw_layers, list) or not raw_layers:
        raise ConfigError("no layers: add at least one [[layer]] with a name and paths")

    layers = []
    for index, raw in enumerate(raw_layers, start=1):
        where = f"layer {index}"
        if not isinstance(raw, dict):
            raise ConfigError(f"{where}: write it as [[layer]]")
        _only(raw, _LAYER, where)
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise ConfigError(f"{where}: needs a name")
        where = f"layer '{name}'"
        paths = _strings(raw.get("paths", []), f"{where}: paths")
        if not paths:
            raise ConfigError(f"{where}: needs paths, for example paths = [\"src/core/**\"]")
        hint = raw.get("hint", "")
        if not isinstance(hint, str):
            raise ConfigError(f"{where}: hint must be a string")
        layers.append(
            Layer(
                name=name,
                paths=paths,
                may_use=_strings(raw.get("may_use", []), f"{where}: may_use"),
                pure=_flag(raw.get("pure", False), f"{where}: pure"),
                forbid_external=_strings(raw.get("forbid_external", []), f"{where}: forbid_external"),
                hint=hint,
            )
        )

    names = [layer.name for layer in layers]
    for name in names:
        if names.count(name) > 1:
            raise ConfigError(f"layer '{name}' is defined more than once")
    for layer in layers:
        for used in layer.may_use:
            if used not in names:
                raise ConfigError(f"layer '{layer.name}': may_use names '{used}', which is not a layer ({', '.join(names)})")
            if used == layer.name:
                raise ConfigError(f"layer '{layer.name}': may_use lists the layer itself; a layer may always use itself")

    purity = data.get("purity", {})
    _only(purity, {"allow", "forbid"}, "[purity]")
    python = data.get("python", {})
    _only(python, {"roots"}, "[python]")
    cpp = data.get("cpp", {})
    _only(cpp, {"include_dirs"}, "[cpp]")
    javascript = data.get("javascript", {})
    _only(javascript, {"aliases"}, "[javascript]")
    aliases = javascript.get("aliases", {})
    if not isinstance(aliases, dict) or not all(isinstance(v, str) for v in aliases.values()):
        raise ConfigError("[javascript] aliases: expected a table of prefix = \"directory\"")

    return Config(
        layers=layers,
        strict=_flag(data.get("strict", False), "strict"),
        include_tests=_flag(data.get("include_tests", False), "include_tests"),
        exclude=_strings(data.get("exclude", []), "exclude"),
        purity_allow=_strings(purity.get("allow", []), "[purity] allow"),
        purity_forbid=_strings(purity.get("forbid", []), "[purity] forbid"),
        python_roots=_strings(python.get("roots", []), "[python] roots"),
        cpp_include_dirs=_strings(cpp.get("include_dirs", []), "[cpp] include_dirs"),
        js_aliases=dict(aliases),
    )
