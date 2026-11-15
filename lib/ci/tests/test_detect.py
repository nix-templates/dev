"""Finding a checkout's languages. Run with: PYTHONPATH=.:../layers:../../mcp python -m unittest discover -s tests"""

import unittest

from support import MARKS, REAL_MARKS, checkout

from ci import detect

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
    "nix": ({"default.nix": "{ }\n"}, {"nix"}),
    "node": ({"index.js": "export {}\n"}, {"node"}),
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
    "python": ({"app.py": "print(1)\n"}, {"python"}),
    "qml": ({"Main.qml": "import QtQuick\nItem { }\n"}, {"qml"}),
    "r": ({"analysis.R": "print(1)\n"}, {"r"}),
    "racket": ({"main.rkt": "#lang racket\n"}, {"racket"}),
    "ruby": ({"app.rb": "puts 1\n"}, {"ruby"}),
    "rust": ({"Cargo.toml": '[package]\nname = "sample"\n', "src/main.rs": "fn main() {}\n"}, {"rust"}),
    "scala": ({"Main.scala": "object Main\n"}, {"scala"}),
    "shell": ({"run.sh": "echo 1\n"}, {"shell"}),
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


def found(files: dict[str, str], marks: dict = MARKS) -> list[str]:
    return list(detect.found(checkout(files, commit=False), marks))


@unittest.skipUnless(REAL_MARKS, "needs DEV_CI_MARKS, the marks of every language as lib.marks gives them")
class EveryLanguage(unittest.TestCase):
    def test_every_language_of_the_library_has_a_sample_or_is_never_found(self):
        self.assertEqual(set(SAMPLES) | NEVER, set(REAL_MARKS))
        self.assertFalse(set(SAMPLES) & NEVER)

    def test_each_sample_is_found_as_its_language(self):
        for name, (files, expected) in SAMPLES.items():
            with self.subTest(language=name):
                self.assertEqual(set(found(files, REAL_MARKS)), expected)

    def test_what_is_never_found_names_no_files(self):
        for name in NEVER:
            self.assertEqual(REAL_MARKS[name]["marks"], [], name)

    def test_every_sample_at_once_finds_all_but_what_another_stands_in_for(self):
        files = {f"{name}/{path}": text for name, (sample, _) in SAMPLES.items() for path, text in sample.items() if not path.startswith(".")}
        files[".github/workflows/check.yml"] = "on: push\n"
        stood_in_for = {other for name in SAMPLES for other in REAL_MARKS[name]["insteadOf"]}
        self.assertEqual(set(found(files, REAL_MARKS)), set(SAMPLES) - stood_in_for)


class Files(unittest.TestCase):
    def test_languages_come_back_sorted_with_their_files(self):
        root = checkout({"b.sh": "echo 1\n", "a.py": "print(1)\n", "lib/c.py": "print(2)\n"}, commit=False)
        self.assertEqual(detect.found(root, MARKS), {"python": ["a.py", "lib/c.py"], "shell": ["b.sh"]})

    def test_a_script_without_an_extension_is_read_by_its_first_line(self):
        self.assertEqual(found({"bin/run": "#!/usr/bin/env bash\necho 1\n"}), ["shell"])
        self.assertEqual(found({"bin/tool": "#!/usr/bin/env python3\nprint(1)\n"}), ["python"])
        self.assertEqual(found({"bin/notes": "just words\n"}), [])

    def test_a_checkout_with_nothing_the_library_knows_has_no_language(self):
        self.assertEqual(found({"LICENSE": "All rights reserved.\n", "data.csv": "a,b\n"}), [])

    def test_what_git_ignores_and_what_is_vendored_does_not_count(self):
        files = {".gitignore": "out/\n", "out/made.py": "print(1)\n", "node_modules/dep/index.js": "export {}\n", "vendor/dep.sh": "echo 1\n"}
        self.assertEqual(found(files), [])

    def test_a_file_that_architecture_does_not_read_as_a_language_is_not_that_language(self):
        # Qt names its translations .ts, and Perl and Prolog share .pl.
        self.assertEqual(found({"notes_nl.ts": '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n<TS version="2.1"/>\n'}), [])
        self.assertEqual(found({"facts.pl": "likes(a, b).\n", "run.pl": "use strict;\nprint 1;\n"}, {"perl": {"marks": None, "insteadOf": []}}), ["perl"])

    def test_a_hidden_directory_that_git_lists_counts(self):
        self.assertEqual(found({".github/workflows/check.yml": "on: push\n"}), ["github-actions"])
        self.assertEqual(found({".hooks/pre-commit.sh": "echo 1\n"}), ["shell"])


class Marks(unittest.TestCase):
    def test_a_mark_without_a_slash_is_a_file_name_anywhere(self):
        self.assertTrue(detect.marked("*.md", "docs/guide/intro.md"))
        self.assertTrue(detect.marked("Dockerfile.*", "images/Dockerfile.dev"))
        self.assertFalse(detect.marked("*.md", "docs/md/notes.txt"))
        self.assertFalse(detect.marked("deno.json", "deno.jsonc"))

    def test_a_mark_with_a_slash_is_a_path_from_the_top(self):
        self.assertTrue(detect.marked(".github/workflows/*.yml", ".github/workflows/check.yml"))
        self.assertFalse(detect.marked(".github/workflows/*.yml", "docs/.github/workflows/check.yml"))
        self.assertFalse(detect.marked(".github/workflows/*.yml", ".github/dependabot.yml"))

    def test_a_language_with_marks_is_found_by_them_alone(self):
        self.assertEqual(found({"index.ts": "export {}\n"}), ["node"])
        self.assertEqual(found({"tsconfig.json": "{}\n"}), ["typescript"])
        self.assertEqual(found({"README.md": "# Sample\n"}), ["markdown"])

    def test_a_language_stands_in_for_the_ones_it_names(self):
        self.assertEqual(found({"index.js": "export {}\n"}), ["node"])
        self.assertEqual(found({"deno.json": "{}\n", "index.js": "export {}\n", "mod.ts": "export {}\n"}), ["deno"])

    def test_a_language_with_no_marks_at_all_is_never_found(self):
        self.assertEqual(found({"main.tf": 'resource "null_resource" "a" {}\n'}), ["terraform"])

    def test_standing_in_does_not_depend_on_the_order_of_names(self):
        read = {"javascript": ["a.js"]}
        marks = {
            "a-last": {"marks": ["a.js"], "insteadOf": ["node"]},
            "node": {"marks": None, "insteadOf": []},
            "z-first": {"marks": ["a.js"], "insteadOf": ["a-last"]},
        }
        self.assertEqual(list(detect.among(["a.js"], read, marks)), ["z-first"])


if __name__ == "__main__":
    unittest.main()
