"""An MCP server for nix-templates/dev.

It lets an agent see which languages the library knows, what each one brings,
and write the flake for a project that uses them. It speaks the Model Context
Protocol over stdin and stdout, one JSON-RPC message per line, and needs
nothing but the Python standard library.

    nix run github:nix-templates/dev#mcp
"""

import difflib
import json
import os
import sys

from layers.cli import languages as read_languages
from layers.config import ConfigError, parse

VERSION = "0.1.0"
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
NIXPKGS = "https://flakehub.com/f/NixOS/nixpkgs/0.1"
SYSTEMS = ["x86_64-linux", "aarch64-linux", "aarch64-darwin"]

INSTRUCTIONS = """nix-templates/dev gives a project a Nix dev shell with the compilers, language servers, \
linters, formatters, scanners and test tools of every language it is written in, and five commands \
that work the same in every project: quality, style (style --check), security, architecture and tests \
(tests --coverage, --mutation and more where the language has a tool).

To set a project up: call list_languages, pick the names that match the project's files, look at \
describe_language for anything you need to know about one, then call generate_flake and write the \
files it returns. architecture_rules writes an architecture.toml (layers and a functional core) \
that `architecture` enforces. After writing the files: `git add` them, then `nix develop`."""


# Templates whose sources `architecture` reads under another name than their own.
READ_AS = {
    "bun": ["javascript"],
    "deno": ["javascript"],
    "node": ["javascript"],
    "typescript": ["javascript"],
    "web": ["javascript"],
    "c-cpp": ["cpp", "cmake"],
    "platformio": ["cpp"],
    "hashi": ["terraform"],
    "hdl": ["verilog", "vhdl"],
    "jupyter": ["python"],
    "lean4": ["lean"],
    "opa": ["rego"],
    "pulumi": ["javascript", "python", "go"],
    "swi-prolog": ["prolog"],
    "vlang": ["v"],
}


def read_as(name: str) -> list[str]:
    """The readers `architecture` has for a template's sources; empty when there is nothing to read."""
    readers = {reader for reader, _ in read_languages()}
    return READ_AS.get(name, [name] if name in readers else [])


class ToolError(Exception):
    pass


def load_catalogue() -> dict:
    path = os.environ.get("DEV_CATALOGUE") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not path:
        raise SystemExit("server.py: set DEV_CATALOGUE to the catalogue file, or pass it as the first argument")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def known(catalogue: dict, names: list) -> list[str]:
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise ToolError("languages must be a list of names, for example [\"rust\", \"python\"]")
    for name in names:
        if name not in catalogue:
            close = difflib.get_close_matches(name, catalogue, n=3)
            hint = f" Did you mean {', '.join(close)}?" if close else ""
            raise ToolError(f"there is no language '{name}'.{hint} list_languages shows every name.")
    return names


def list_languages(catalogue: dict, _arguments: dict) -> dict:
    return {
        "languages": [
            {
                "name": name,
                "description": entry["description"],
                "architecture_reads": read_as(name),
                "architecture_tools": bool(entry["architecture"]),
                "tests": sorted(entry["tests"]),
            }
            for name, entry in sorted(catalogue.items())
        ],
        "note": "tests lists the modes `tests` has for that language: run is plain `tests`, the others are `tests --<mode>`. "
        "Every language also gets typos, editorconfig-checker and gitleaks, and `architecture` for architecture.toml. "
        "architecture_reads names the readers `architecture` has for that language's sources, so architecture.toml applies to them. "
        "architecture_tools says the language also has a tool of its own that `architecture` runs after the rules.",
    }


def describe_language(catalogue: dict, arguments: dict) -> dict:
    (name,) = known(catalogue, [arguments.get("name")])
    entry = catalogue[name]
    return {
        "name": name,
        "description": entry["description"],
        "tools": entry["tools"],
        "commands": {
            "quality": entry["quality"],
            "style": entry["style"],
            "security": entry["security"] + ("run semgrep scan --config auto --error --quiet .\n" if entry["semgrep"] else ""),
            "architecture (after the rules in architecture.toml)": "".join(entry["architecture"]),
            **{("tests" if mode == "run" else f"tests --{mode}"): "".join(blocks) for mode, blocks in entry["tests"].items()},
        },
        "nixpkgs_config": entry["nixpkgsConfig"],
        "reading_the_commands": "`when FILE cmd` runs cmd only when FILE exists; `when_any PATTERN cmd` when a file matches; "
        "`when_has FILE TEXT cmd` when FILE contains TEXT; `run_on PATTERN cmd` passes the matching files; `run cmd` always runs. "
        "So most tools switch on when the project has their config file.",
    }


def nix_list(items: list[str], indent: int) -> str:
    pad = " " * indent
    return "[\n" + "".join(f"{pad}  {item}\n" for item in items) + f"{pad}]"


def generate_flake(catalogue: dict, arguments: dict) -> dict:
    languages = known(catalogue, arguments.get("languages"))
    systems = arguments.get("systems") or SYSTEMS
    nixpkgs = arguments.get("nixpkgs") or NIXPKGS
    extra = arguments.get("extra_tools") or []
    checks = bool(arguments.get("checks"))
    venv = bool(arguments.get("python_venv"))
    description = arguments.get("description") or "A development environment for " + ", ".join(languages)
    for value, what in ((systems, "systems"), (extra, "extra_tools")):
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise ToolError(f"{what} must be a list of strings")
    for attr in extra:
        if not all(part.replace("-", "_").replace("'", "_").isidentifier() for part in attr.split(".")):
            raise ToolError(f"extra_tools: '{attr}' is not a nixpkgs attribute name such as jq or python3Packages.requests")

    config = []
    for name in languages:
        for line in catalogue[name]["nixpkgsConfig"]:
            if line not in config:
                config.append(line)
    if config:
        body = "".join(f"              {line}\n" for line in config)
        pkgs_import = f"            pkgs = import inputs.nixpkgs {{\n              inherit system;\n{body}            }};"
    else:
        pkgs_import = "            pkgs = import inputs.nixpkgs { inherit system; };"

    options = []
    if extra:
        options.append(f"          extraTools = with pkgs; {nix_list(extra, 10)};")
    if venv:
        options.append("          # A .venv next to the project, made and activated on entering the shell.\n          options.pythonVenv = true;")
    if checks:
        options.append("          src = self;")
    option_text = "".join("\n" + line for line in options)
    check_text = (
        "\n      # `nix flake check` checks the rules in architecture.toml.\n"
        "      checks = forEachSupportedSystem ({ pkgs, ... }: (project pkgs).checks);\n"
        if checks
        else ""
    )

    # `self` only when the flake uses it: deadnix reports an argument that is never used.
    outputs_arguments = "{ self, ... }@inputs" if checks else "inputs"

    flake = f"""{{
  description = {json.dumps(description)};

  inputs = {{
    nixpkgs.url = {json.dumps(nixpkgs)};

    # The tools and checks. `nix flake update dev` brings in newer ones.
    dev = {{
      url = "github:nix-templates/dev";
      inputs.nixpkgs.follows = "nixpkgs";
    }};
  }};

  outputs =
    {outputs_arguments}:

    let
      supportedSystems = {nix_list([json.dumps(s) for s in systems], 6)};

      forEachSupportedSystem =
        f:
        inputs.nixpkgs.lib.genAttrs supportedSystems (
          system:
          f {{
            inherit system;
{pkgs_import}
          }}
        );

      # What this project is written in. Each name adds that language's tools to
      # the shell, and its checks to `quality`, `style`, `security`, `architecture`
      # and `tests`.
      project =
        pkgs:
        inputs.dev.lib.mkProject {{
          inherit pkgs;
          languages = {nix_list([json.dumps(n) for n in languages], 10)};{option_text}
        }};
    in
    {{
      devShells = forEachSupportedSystem (
        {{ pkgs, ... }}:
        {{
          default = (project pkgs).devShell;
        }}
      );
{check_text}
      formatter = forEachSupportedSystem ({{ pkgs, ... }}: pkgs.nixfmt);
    }};
}}
"""
    files = {
        "flake.nix": flake,
        ".envrc": "use flake\n\nwatch_file flake.nix\nwatch_file flake.lock\n",
    }
    steps = ["Write the files, then `git add` them: a flake only sees files git knows about.", "`nix develop`, or `direnv allow` with direnv installed."]
    if checks:
        steps.insert(0, "checks needs an architecture.toml: call architecture_rules and write its file too.")
    if "rust" in languages:
        steps.append("Rust: the toolchain comes from nixpkgs. To pin one, pass `rustToolchain` to mkProject (see the rust template).")
    modes = sorted({mode for name in languages for mode in catalogue[name]["tests"]} - {"run"})
    return {
        "files": files,
        "commands": ["quality", "style", "style --check", "security", "architecture", "tests"] + [f"tests --{mode}" for mode in modes],
        "next": steps,
    }


REFERENCE = """architecture.toml divides the code into layers and says what each may use.

A file may use files in its own layer and in the layers its layer lists under may_use, and nothing else. \
The first layer whose paths match a file is that file's layer, so list the narrow ones first. \
In paths, * stays inside one path segment and ** crosses segments; a directory name matches everything below it.

pure = true marks a functional core: the same input gives the same output and nothing outside the function changes. \
Such a layer may not touch files, the network, processes, the clock, the environment, randomness, threads or shared mutable state.

forbid_external lists packages a layer may not depend on. hint is added to that layer's failure messages. \
apart = true keeps the entries under paths apart: files under one entry may not use files under another, \
which is how to say that apps or plugins do not use each other.

`architecture` checks these rules. It reads the sources of these languages itself: {languages}. \
It reads them as text, so it is close, not exact: names built at run time and build-system path mappings are not followed. \
After the rules it runs a language's own architecture tool when the project has that tool's config \
(describe_language shows which).

roots lists directories that imports are resolved from, for when a language's usual ones (the repository root, src, lib) do not fit. \
purity_allow and purity_forbid take entries off, and add entries to, what a pure layer may not touch.

Adopting it in existing code: `architecture --explain` shows which files are in which layer, `architecture --accept` writes today's \
violations to architecture-baseline.json. After that only new violations fail, and the baseline may only get shorter.""".format(
    languages=", ".join(name for name, _ in read_languages())
)


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def architecture_rules(_catalogue: dict, arguments: dict) -> dict:
    layers = arguments.get("layers")
    if not layers:
        return {"reference": REFERENCE, "example_arguments": {"layers": [
            {"name": "core", "paths": ["src/core"], "pure": True},
            {"name": "adapters", "paths": ["src/adapters"], "may_use": ["core"]},
            {"name": "app", "paths": ["src"], "may_use": ["core", "adapters"]},
        ]}}
    if not isinstance(layers, list) or not all(isinstance(layer, dict) for layer in layers):
        raise ToolError("layers must be a list of objects with name and paths")
    out = ["version = 1"]
    if arguments.get("strict"):
        out.append("strict = true")
    if arguments.get("exclude"):
        out.append("exclude = [" + ", ".join(toml_string(str(item)) for item in arguments["exclude"]) + "]")
    for layer in layers:
        out += ["", "[[layer]]"]
        for key in ("name", "hint"):
            if layer.get(key):
                out.append(f"{key} = {toml_string(str(layer[key]))}")
        for key in ("paths", "may_use", "forbid_external"):
            if layer.get(key):
                if not isinstance(layer[key], list):
                    raise ToolError(f"layer {layer.get('name', '?')}: {key} must be a list")
                out.append(f"{key} = [" + ", ".join(toml_string(str(item)) for item in layer[key]) + "]")
        if layer.get("pure"):
            out.append("pure = true")
        if layer.get("apart"):
            out.append("apart = true")
        unknown = sorted(set(layer) - {"name", "hint", "paths", "may_use", "forbid_external", "pure", "apart"})
        if unknown:
            raise ToolError(f"layer {layer.get('name', '?')}: unknown key {', '.join(unknown)}")
    for table, key, argument in (("sources", "roots", "roots"), ("purity", "allow", "purity_allow"), ("purity", "forbid", "purity_forbid")):
        if arguments.get(argument):
            if not isinstance(arguments[argument], list):
                raise ToolError(f"{argument} must be a list")
            if f"[{table}]" not in out:
                out += ["", f"[{table}]"]
            out.append(f"{key} = [" + ", ".join(toml_string(str(item)) for item in arguments[argument]) + "]")
    text = "\n".join(out) + "\n"
    try:
        parse(text)
    except ConfigError as error:
        raise ToolError(f"these rules are not valid: {error}") from error
    return {
        "files": {"architecture.toml": text},
        "next": ["`architecture --explain` to see which files land in which layer.", "`architecture` to check; `architecture --accept` to adopt the rules in existing code."],
    }


STRINGS = {"type": "array", "items": {"type": "string"}}
TOOLS = {
    "list_languages": (
        list_languages,
        "Every language and technology the library has tools for, with a one-line description, whether it has architecture tools, and which test modes it has.",
        {"type": "object", "properties": {}},
    ),
    "describe_language": (
        describe_language,
        "One language in full: every tool in its shell, and exactly what quality, style, security, architecture and tests run for it and which config file switches each tool on.",
        {"type": "object", "properties": {"name": {"type": "string", "description": "A name from list_languages, such as rust."}}, "required": ["name"]},
    ),
    "generate_flake": (
        generate_flake,
        "Write the flake.nix (and .envrc) for a project that takes its dev shell from this library. Returns the files as text; it writes nothing itself.",
        {
            "type": "object",
            "properties": {
                "languages": {**STRINGS, "description": "Names from list_languages, in the order their checks should run."},
                "extra_tools": {**STRINGS, "description": "More nixpkgs packages for the shell, as attribute names: jq, python3Packages.requests."},
                "checks": {"type": "boolean", "description": "Also expose `architecture` as a flake check. Needs an architecture.toml."},
                "python_venv": {"type": "boolean", "description": "For python and jupyter: make and activate a .venv on entering the shell."},
                "systems": {**STRINGS, "description": f"Default: {', '.join(SYSTEMS)}."},
                "nixpkgs": {"type": "string", "description": f"The nixpkgs flake URL. Default: {NIXPKGS} (unstable)."},
                "description": {"type": "string", "description": "The flake's description."},
            },
            "required": ["languages"],
        },
    ),
    "architecture_rules": (
        architecture_rules,
        "Write an architecture.toml from a list of layers, checked by the same parser `architecture` uses. Called without layers it returns the format's reference.",
        {
            "type": "object",
            "properties": {
                "layers": {
                    "type": "array",
                    "description": "In order: the first layer whose paths match a file is that file's layer.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "paths": STRINGS,
                            "may_use": {**STRINGS, "description": "Names of the layers this one may use."},
                            "pure": {"type": "boolean", "description": "A functional core: no I/O, clock, environment, randomness or shared state."},
                            "apart": {"type": "boolean", "description": "Each entry in paths stands on its own: files under one may not use files under another."},
                            "forbid_external": {**STRINGS, "description": "Packages this layer may not depend on."},
                            "hint": {"type": "string", "description": "Added to this layer's failure messages."},
                        },
                        "required": ["name", "paths"],
                    },
                },
                "strict": {"type": "boolean", "description": "Fail on source files that are in no layer."},
                "exclude": {**STRINGS, "description": "Paths to leave out."},
                "roots": {**STRINGS, "description": "Directories imports are resolved from, besides each language's usual ones."},
                "purity_allow": {**STRINGS, "description": "Take these off what a pure layer may not touch."},
                "purity_forbid": {**STRINGS, "description": "Add these to what a pure layer may not touch."},
            },
        },
    ),
}


def handle(catalogue: dict, message: dict) -> dict | None:
    """The reply to one JSON-RPC message, or None for a notification."""
    identifier = message.get("id")
    method = message.get("method")

    def reply(result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": identifier, "result": result}

    def fail(code: int, text: str) -> dict:
        return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": text}}

    if "id" not in message:
        return None
    if method == "initialize":
        asked = (message.get("params") or {}).get("protocolVersion")
        return reply(
            {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "nix-templates-dev", "version": VERSION},
                "instructions": INSTRUCTIONS,
            }
        )
    if method == "ping":
        return reply({})
    if method == "tools/list":
        return reply({"tools": [{"name": name, "description": text, "inputSchema": schema} for name, (_, text, schema) in TOOLS.items()]})
    if method == "tools/call":
        params = message.get("params") or {}
        tool = TOOLS.get(params.get("name"))
        if tool is None:
            return fail(-32602, f"unknown tool: {params.get('name')}")
        try:
            result = tool[0](catalogue, params.get("arguments") or {})
            return reply({"content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}], "isError": False})
        except ToolError as error:
            return reply({"content": [{"type": "text", "text": str(error)}], "isError": True})
    return fail(-32601, f"method not found: {method}")


def serve(catalogue: dict, lines, out) -> None:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            replies = [{"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}]
        else:
            batch = message if isinstance(message, list) else [message]
            replies = [r for r in (handle(catalogue, m) for m in batch if isinstance(m, dict)) if r is not None]
            if isinstance(message, list) and replies:
                replies = [replies]
        for item in replies:
            out.write(json.dumps(item, ensure_ascii=False) + "\n")
            out.flush()


if __name__ == "__main__":
    serve(load_catalogue(), sys.stdin, sys.stdout)
