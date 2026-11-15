"""One small checkout per language of the library.

The tests of `ci` find each language in its sample. The `systems` workflow
puts a template's sample into the project it tries, so that the language's
own tools have files to run on.

    python3 samples.py TEMPLATE DIRECTORY    write a template's sample into a directory
"""

import os
import sys

# The samples that are held to being clean (CLEAN, below) have a test in them,
# so that `tests` has one to run. They are written the way their own
# formatters write them.
NIX = {
    "default.nix": "{ }\n",
    "tests/default.nix": "{\n  testAnswer = {\n    expr = 1 + 0;\n    expected = 1;\n  };\n}\n",
}
NODE = {
    "index.js": "export function answer() {\n  return 1;\n}\n",
    "index.test.js": (
        'import assert from "node:assert";\n'
        'import test from "node:test";\n'
        'import { answer } from "./index.js";\n'
        "\n"
        'test("the answer is 1", () => {\n'
        "  assert.strictEqual(answer(), 1);\n"
        "});\n"
    ),
    "package.json": '{\n  "name": "sample",\n  "private": true,\n  "type": "module",\n  "scripts": {\n    "test": "node --test"\n  }\n}\n',
}
PYTHON = {
    "app.py": "def answer():\n    return 1\n",
    # Without `assert`: bandit reports every one of them.
    "tests/test_app.py": (
        "from app import answer\n"
        "\n"
        "\n"
        "def test_answer():\n"
        "    if answer() != 1:\n"
        '        raise AssertionError("the answer is not 1")\n'
    ),
}
RUST = {
    "Cargo.toml": '[package]\nname = "sample"\nversion = "0.1.0"\nedition = "2021"\n',
    "src/main.rs": (
        "fn answer() -> u32 {\n"
        "    1\n"
        "}\n"
        "\n"
        "fn main() {\n"
        '    println!("{}", answer());\n'
        "}\n"
        "\n"
        "#[cfg(test)]\n"
        "mod tests {\n"
        "    use super::answer;\n"
        "\n"
        "    #[test]\n"
        "    fn the_answer_is_one() {\n"
        "        assert_eq!(answer(), 1);\n"
        "    }\n"
        "}\n"
    ),
}
SHELL = {
    "run.sh": "#!/usr/bin/env bash\necho 1\n",
    "tests/run.bats": '#!/usr/bin/env bats\n\n@test "run.sh says 1" {\n  run bash run.sh\n  [ "$output" = 1 ]\n}\n',
}

# One checkout per language of the library, and what must be found in it.
# Where two names come back, the files really are both.
SAMPLES = {
    "ansible": ({"ansible.cfg": "[defaults]\n", "site.yml": "- hosts: all\n"}, {"ansible"}),
    "assembly": ({"boot.asm": "mov eax, 1\n"}, {"assembly"}),
    "bun": ({"bun.lock": "{}\n", "index.ts": "export {}\n"}, {"bun"}),
    "c-cpp": ({"main.c": "int main(void) { return 0; }\n", "CMakeLists.txt": "project(sample)\n"}, {"c-cpp"}),
    "clojure": ({"core.clj": "(ns core)\n"}, {"clojure"}),
    "crystal": ({"app.cr": 'puts "hello"\n'}, {"crystal"}),
    "csharp": ({"Program.cs": "class Program { }\n"}, {"csharp"}),
    "cue": ({"schema.cue": "package schema\n"}, {"cue"}),
    "dart": ({"main.dart": "void main() {}\n"}, {"dart"}),
    "deno": ({"deno.json": "{}\n", "main.ts": "export {}\n"}, {"deno"}),
    "dhall": ({"config.dhall": "{ a = 1 }\n"}, {"dhall"}),
    "docker": ({"Dockerfile": "FROM scratch\n"}, {"docker"}),
    "elixir": ({"app.ex": "defmodule App do\nend\n"}, {"elixir"}),
    "elm": ({"Main.elm": "module Main exposing (main)\n"}, {"elm"}),
    "erlang": ({"app.erl": "-module(app).\n"}, {"erlang"}),
    "fortran": ({"main.f90": "program main\nend program main\n"}, {"fortran"}),
    "fsharp": ({"Program.fs": "module Program\n"}, {"fsharp"}),
    "github-actions": ({".github/workflows/check.yml": "on: push\n"}, {"github-actions"}),
    "gleam": ({"app.gleam": "pub fn main() {}\n"}, {"gleam"}),
    "go": ({"main.go": "package main\n"}, {"go"}),
    "graphql": ({"schema.graphql": "type Query { a: Int }\n"}, {"graphql"}),
    "groovy": ({"build.groovy": "println 'hello'\n"}, {"groovy"}),
    "haskell": ({"Main.hs": "module Main where\n"}, {"haskell"}),
    "haxe": ({"Main.hx": "class Main { }\n"}, {"haxe"}),
    "hdl": ({"top.vhd": "entity top is\nend entity;\n", "adder.sv": "module adder;\nendmodule\n"}, {"hdl"}),
    "java": ({"Main.java": "class Main { }\n"}, {"java"}),
    "julia": ({"main.jl": "println(1)\n"}, {"julia"}),
    "jupyter": ({"notebook.ipynb": '{"cells": []}\n'}, {"jupyter", "python"}),
    "kotlin": ({"Main.kt": "fun main() {}\n"}, {"kotlin"}),
    "kubernetes": ({"Chart.yaml": "name: sample\n"}, {"kubernetes"}),
    "latex": ({"paper.tex": "\\documentclass{article}\n"}, {"latex"}),
    "lean4": ({"Main.lean": "def main : IO Unit := pure ()\n"}, {"lean4"}),
    "lua": ({"init.lua": "print(1)\n"}, {"lua"}),
    "markdown": ({"README.md": "# Sample\n"}, {"markdown"}),
    "nickel": ({"config.ncl": "{ a = 1 }\n"}, {"nickel"}),
    "nim": ({"main.nim": "echo 1\n"}, {"nim"}),
    "nix": (NIX, {"nix"}),
    "node": (NODE, {"node"}),
    "ocaml": ({"main.ml": "let () = ()\n"}, {"ocaml"}),
    "odin": ({"main.odin": "package main\n"}, {"odin"}),
    "opa": ({"policy.rego": "package policy\n"}, {"opa"}),
    "perl": ({"script.pl": "use strict;\nprint 1;\n"}, {"perl"}),
    "php": ({"index.php": "<?php echo 1;\n"}, {"php"}),
    "platformio": ({"platformio.ini": "[env:native]\n", "src/main.cpp": "int main() { return 0; }\n"}, {"platformio"}),
    "powershell": ({"build.ps1": "Write-Output 1\n"}, {"powershell"}),
    "protobuf": ({"api.proto": 'syntax = "proto3";\n'}, {"protobuf"}),
    "pulumi": ({"Pulumi.yaml": "name: sample\n", "index.ts": "export {}\n"}, {"pulumi", "node"}),
    "purescript": ({"Main.purs": "module Main where\n"}, {"purescript"}),
    "python": (PYTHON, {"python"}),
    "qml": ({"Main.qml": "import QtQuick\nItem { }\n"}, {"qml"}),
    "r": ({"analysis.R": "print(1)\n"}, {"r"}),
    "racket": ({"main.rkt": "#lang racket\n"}, {"racket"}),
    "ruby": ({"app.rb": "puts 1\n"}, {"ruby"}),
    "rust": (RUST, {"rust"}),
    "scala": ({"Main.scala": "object Main\n"}, {"scala"}),
    "shell": (SHELL, {"shell"}),
    "solidity": ({"Token.sol": "contract Token { }\n"}, {"solidity"}),
    "sql": ({"schema.sql": "select 1;\n"}, {"sql"}),
    "swi-prolog": ({"facts.pl": ":- module(facts, []).\nlikes(a, b).\n"}, {"swi-prolog"}),
    "swift": ({"main.swift": "print(1)\n"}, {"swift"}),
    "terraform": ({"main.tf": 'resource "null_resource" "a" {}\n'}, {"terraform"}),
    "typescript": ({"tsconfig.json": "{}\n", "index.ts": "export {}\n"}, {"typescript"}),
    "typst": ({"paper.typ": "= Title\n"}, {"typst"}),
    "vlang": ({"main.v": "module main\n\nfn main() {}\n"}, {"vlang"}),
    "web": ({"index.html": "<!doctype html>\n", "style.css": "body { }\n"}, {"web"}),
    "zig": ({"main.zig": "pub fn main() void {}\n"}, {"zig"}),
}

# What no file gives away: a project names these in a flake of its own.
NEVER = {"empty", "hashi", "presenterm"}

# A template that is not one language: the languages its flake names.
TEMPLATES = {"project": ("nix", "shell")}

# The templates whose sample is clean: in a project fresh from the template,
# with the sample in it, each of the five commands ends with 0, and `tests`
# has a test to run. The `systems` workflow holds these to that on every system.
CLEAN = ("shell", "python", "rust", "node", "nix", "project")


def write(template: str, directory: str) -> list[str]:
    """Write the sample files of a template into a directory, and say which."""
    written = []
    for language in TEMPLATES.get(template, (template,)):
        files, _ = SAMPLES.get(language, ({}, set()))
        for path, text in files.items():
            full = os.path.join(directory, path)
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "w", encoding="utf-8") as handle:
                handle.write(text)
            written.append(path)
    return written


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: samples.py TEMPLATE DIRECTORY")
    files = write(sys.argv[1], sys.argv[2])
    print(f"sample of {sys.argv[1]}: {', '.join(files) if files else 'none, no file gives this template away'}")
