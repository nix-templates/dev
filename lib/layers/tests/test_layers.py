"""Tests for layers --check. Run with: PYTHONPATH=. python -m unittest discover -s tests"""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import textwrap
import unittest

from layers import baseline, cli, rust
from layers.config import ConfigError, parse
from layers.effects import covers
from layers.walk import glob_match


def tree(files: dict[str, str]) -> str:
    root = tempfile.mkdtemp(prefix="layers-test-")
    for path, text in files.items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(text).lstrip("\n"))
    return root


MODES = {"--check", "--accept", "--prune", "--explain"}


def call(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = cli.main(list(argv))
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue()


def run(root: str, *args: str) -> tuple[int, str]:
    """`layers --check` on root, or the mode named in args."""
    mode = [] if MODES & set(args) else ["--check"]
    return call(*mode, "--root", root, *args)


def found(root: str) -> set[tuple[str, str, str]]:
    code, out = run(root, "--format", "json", "--no-baseline")
    return {(v["rule"], v["file"], v["target"]) for v in json.loads(out)["new"]}


class Globs(unittest.TestCase):
    def test_directory_and_double_star_match_everything_below(self):
        self.assertTrue(glob_match("src/shell", "src/shell/a/b.rs"))
        self.assertTrue(glob_match("src/shell/**", "src/shell/a/b.rs"))
        self.assertFalse(glob_match("src/shell", "src/shell_extra/a.rs"))

    def test_dot_is_the_whole_repository(self):
        self.assertTrue(glob_match(".", "src/a.rs"))
        self.assertTrue(glob_match("./src", "src/a.rs"))
        self.assertFalse(glob_match("./src", "lib/a.rs"))

    def test_star_stays_inside_one_segment(self):
        self.assertTrue(glob_match("crates/*-atspi/**", "crates/access-atspi/src/lib.rs"))
        self.assertFalse(glob_match("crates/*/Cargo.toml", "crates/a/b/Cargo.toml"))
        self.assertTrue(glob_match("**/ports/**", "crates/a/src/ports/mod.rs"))
        self.assertTrue(glob_match("**/ports/**", "ports/x.py"))


class Configuration(unittest.TestCase):
    def test_unknown_key_is_refused(self):
        with self.assertRaisesRegex(ConfigError, "unknown key may_uze"):
            parse('[[layer]]\nname = "a"\npaths = ["a"]\nmay_uze = []\n')

    def test_may_use_must_name_a_layer(self):
        with self.assertRaisesRegex(ConfigError, "'b', which is not a layer"):
            parse('[[layer]]\nname = "a"\npaths = ["a"]\nmay_use = ["b"]\n')

    def test_first_matching_layer_wins(self):
        config = parse('[[layer]]\nname = "ports"\npaths = ["src/core/ports"]\n[[layer]]\nname = "core"\npaths = ["src/core"]\n')
        self.assertEqual(config.layer_of("src/core/ports/a.rs").name, "ports")
        self.assertEqual(config.layer_of("src/core/a.rs").name, "core")
        self.assertIsNone(config.layer_of("src/other.rs"))


class RustText(unittest.TestCase):
    def test_strip_blanks_comments_strings_and_chars_but_keeps_lifetimes(self):
        src = 'let a = "std::fs"; // std::net\nlet b: &\'a str = r#"std::env"#; let c = \'"\'; /* std::process */ x'
        code = rust.strip(src)
        self.assertEqual(len(code), len(src))
        for hidden in ("std::fs", "std::net", "std::env", "std::process"):
            self.assertNotIn(hidden, code)
        self.assertIn("&'a str", code)
        self.assertTrue(code.rstrip().endswith("x"))

    def test_use_trees_expand(self):
        self.assertEqual(
            rust.expand_use("crate::{\n a::X as Y,\n b::{self, c::*},\n shell::snap::{self, SnapState},\n}"),
            [["crate", "a", "X"], ["crate", "b"], ["crate", "b", "c"], ["crate", "shell", "snap"], ["crate", "shell", "snap", "SnapState"]],
        )

    def test_test_modules_are_dropped(self):
        code = rust.drop_test_modules("fn a() {}\n#[cfg(test)]\nmod tests {\n use std::fs;\n fn b() { { } }\n}\nfn c() {}\n")
        self.assertNotIn("std::fs", code)
        self.assertIn("fn c()", code)
        self.assertEqual(code.count("\n"), 7)


RUST_WORKSPACE = {
    "Cargo.toml": """
        [workspace]
        members = ["crates/*"]
        [workspace.dependencies]
        plan-core = { path = "crates/core" }
        tokio = "1"
        """,
    "crates/core/Cargo.toml": """
        [package]
        name = "plan-core"
        version = "0.1.0"
        [dependencies]
        serde = "1"
        """,
    "crates/core/src/lib.rs": """
        pub mod day;
        pub fn total(xs: &[u32]) -> u32 { xs.iter().sum() }
        """,
    "crates/core/src/day.rs": """
        use serde::Serialize;
        pub struct Day;
        #[cfg(test)]
        mod tests {
            use std::fs;
            #[test]
            fn reads() { println!("{:?}", fs::read("x")); }
        }
        """,
    "crates/store/Cargo.toml": """
        [package]
        name = "plan-store"
        version = "0.1.0"
        [dependencies]
        plan-core = { workspace = true }
        tokio = { workspace = true }
        """,
    "crates/store/src/lib.rs": """
        use plan_core::day::Day;
        pub fn load() -> Day { let _ = std::fs::read("x"); Day }
        """,
    "architecture.toml": """
        version = 1
        [[layer]]
        name = "core"
        paths = ["crates/core"]
        pure = true
        [[layer]]
        name = "store"
        paths = ["crates/store"]
        may_use = ["core"]
        """,
}


class Rust(unittest.TestCase):
    def test_clean_workspace_passes(self):
        root = tree(RUST_WORKSPACE)
        code, out = run(root)
        self.assertEqual((code, found(root)), (0, set()), out)

    def test_core_depending_on_an_adapter_crate_is_a_layer_violation(self):
        files = dict(RUST_WORKSPACE)
        files["crates/core/Cargo.toml"] += '        plan-store = { path = "../store" }\n'
        files["crates/core/src/lib.rs"] += "        pub fn bad() { plan_store::load(); }\n"
        self.assertEqual(
            found(tree(files)),
            {
                ("layer", "crates/core/Cargo.toml", "crates/store/Cargo.toml"),
                ("layer", "crates/core/src/lib.rs", "crates/store/src/lib.rs"),
            },
        )

    def test_effects_in_a_pure_crate_are_purity_violations(self):
        files = dict(RUST_WORKSPACE)
        files["crates/core/Cargo.toml"] += '        tokio = { workspace = true }\n        chrono = "0.4"\n'
        files["crates/core/src/day.rs"] += """
        use std::{fs, collections::HashMap};
        pub fn now() -> std::time::Instant { println!("now"); Instant::now() }
        static mut COUNT: u32 = 0;
        pub fn there(path: &std::path::Path) -> bool { path.join("x").exists() }
        pub fn zone() { let _ = chrono::Local; }
        """
        self.assertEqual(
            found(tree(files)),
            {
                ("purity", "crates/core/Cargo.toml", "tokio"),
                ("purity", "crates/core/src/day.rs", "std::fs"),
                ("purity", "crates/core/src/day.rs", "println!"),
                ("purity", "crates/core/src/day.rs", "Instant::now"),
                ("purity", "crates/core/src/day.rs", "static mut"),
                ("purity", "crates/core/src/day.rs", "Path::exists"),
                ("purity", "crates/core/src/day.rs", "chrono::Local"),
            },
        )

    def test_a_rust_file_without_a_manifest_fails_instead_of_passing_unread(self):
        files = dict(RUST_WORKSPACE)
        files["architecture.toml"] = 'exclude = ["crates/core/Cargo.toml"]\n' + textwrap.dedent(files["architecture.toml"])
        self.assertIn(("unreadable", "crates/core/src/lib.rs", "-"), found(tree(files)))

    def test_modules_inside_one_crate(self):
        root = tree(
            {
                "Cargo.toml": '[package]\nname = "comp"\nversion = "0.1.0"\n',
                "src/main.rs": "mod render;\nmod shell;\nfn main() {}\n",
                "src/render/mod.rs": "pub mod draw;\n",
                "src/render/draw.rs": "use crate::{\n    shell::snap::{self, SnapState},\n};\nuse super::super::shell::bar::Bar;\npub fn f() { crate::shell::bar::go(); }\n",
                "src/shell/mod.rs": "pub mod snap;\npub mod bar;\nuse crate::render::draw;\n",
                "src/shell/snap.rs": "pub struct SnapState;\n",
                "src/shell/bar.rs": "pub struct Bar;\npub fn go() {}\n",
                "architecture.toml": """
                    [[layer]]
                    name = "render"
                    paths = ["src/render"]
                    [[layer]]
                    name = "shell"
                    paths = ["src/shell"]
                    may_use = ["render"]
                    """,
            }
        )
        self.assertEqual(
            found(root),
            {
                ("layer", "src/render/draw.rs", "src/shell/snap.rs"),
                ("layer", "src/render/draw.rs", "src/shell/bar.rs"),
            },
        )

    def test_a_dependency_is_named_by_its_library_name(self):
        files = dict(RUST_WORKSPACE)
        files["crates/core/Cargo.toml"] += '        [lib]\n        name = "plan"\n'
        files["crates/core/Cargo.toml"] = files["crates/core/Cargo.toml"].replace("[dependencies]", '[dependencies]\n        store-renamed = { package = "plan-store", path = "../store" }')
        files["crates/core/src/lib.rs"] += "        pub fn bad() { store_renamed::load(); }\n"
        files["crates/store/src/lib.rs"] = "use plan::day::Day;\npub fn load() -> Day { Day }\n"
        files["architecture.toml"] = files["architecture.toml"].replace('may_use = ["core"]', "")
        self.assertEqual(
            found(tree(files)),
            {
                ("layer", "crates/core/Cargo.toml", "crates/store/Cargo.toml"),
                ("layer", "crates/core/src/lib.rs", "crates/store/src/lib.rs"),
                ("layer", "crates/store/Cargo.toml", "crates/core/Cargo.toml"),
                ("layer", "crates/store/src/lib.rs", "crates/core/src/day.rs"),
            },
        )

    def test_forbid_external_keeps_a_vendor_crate_out_of_a_layer(self):
        files = dict(RUST_WORKSPACE)
        files["architecture.toml"] = files["architecture.toml"].replace('may_use = ["core"]', 'may_use = ["core"]\n        forbid_external = ["tokio"]')
        self.assertEqual(found(tree(files)), {("external", "crates/store/Cargo.toml", "tokio")})


class Python(unittest.TestCase):
    FILES = {
        "app/__init__.py": "",
        "app/core/__init__.py": "",
        "app/core/plan.py": """
            from dataclasses import dataclass
            from pathlib import PurePath
            from . import rules
            from .rules import limit
            """,
        "app/core/rules.py": "def limit(): return 3\n",
        "app/adapters/__init__.py": "",
        "app/adapters/disk.py": """
            import os
            from app.core import plan
            from ..core.rules import limit
            def save(): print(open("x").read())
            """,
        "tests/test_plan.py": "import os\nfrom app.adapters import disk\n",
        "architecture.toml": """
            [[layer]]
            name = "core"
            paths = ["app/core"]
            pure = true
            [[layer]]
            name = "adapters"
            paths = ["app/adapters"]
            may_use = ["core"]
            """,
    }

    def test_clean_tree_passes(self):
        self.assertEqual(found(tree(self.FILES)), set())

    def test_core_importing_an_adapter_and_doing_io(self):
        files = dict(self.FILES)
        files["app/core/plan.py"] += """
            import subprocess
            from datetime import datetime
            from ..adapters import disk
            from app.adapters.disk import save
            STATE = 0
            def bump():
                global STATE
                STATE += 1
                print(datetime.now())
                return open("x")
            """
        self.assertEqual(
            found(tree(files)),
            {
                ("layer", "app/core/plan.py", "app/adapters/disk.py"),
                ("purity", "app/core/plan.py", "subprocess"),
                ("purity", "app/core/plan.py", "global"),
                ("purity", "app/core/plan.py", "print()"),
                ("purity", "app/core/plan.py", "datetime.now()"),
                ("purity", "app/core/plan.py", "open()"),
            },
        )

    def test_purity_allow_and_forbid(self):
        files = dict(self.FILES)
        files["app/core/plan.py"] += "\n            import logging\n            import numpy\n"
        files["architecture.toml"] += '\n            [purity]\n            allow = ["logging"]\n            forbid = ["numpy"]\n'
        self.assertEqual(found(tree(files)), {("purity", "app/core/plan.py", "numpy")})

    def test_modules_loaded_by_name_or_by_file_are_imports_too(self):
        files = dict(self.FILES)
        files["app/core/rules.py"] = textwrap.dedent(
            """
            import importlib
            import importlib.util
            from pathlib import PurePath
            disk = importlib.import_module("app.adapters.disk")
            spec = importlib.util.spec_from_file_location("disk", PurePath(__file__).with_name("../adapters/disk.py"))
            def limit(): return 3
            """
        )
        self.assertEqual(
            found(tree(files)),
            {("layer", "app/core/rules.py", "app/adapters/disk.py"), ("purity", "app/core/rules.py", "importlib")},
        )
        code, out = run(tree(files), "--no-baseline")
        self.assertIn("(2 times in this file)", out)

    def test_nothing_may_use_test_code(self):
        files = dict(self.FILES)
        files["app/core/rules.py"] = "from tests.test_plan import fixture\ndef limit(): return 3\n"
        files["tests/__init__.py"] = ""
        self.assertEqual(found(tree(files)), {("layer", "app/core/rules.py", "tests/test_plan.py")})
        # A layer for the tests puts them under the ordinary rules.
        files["architecture.toml"] = textwrap.dedent(files["architecture.toml"]).replace(
            'pure = true', 'pure = true\nmay_use = ["checks"]'
        ) + '[[layer]]\nname = "checks"\npaths = ["tests"]\n'
        self.assertEqual(found(tree(files)), set())

    def test_scripts_in_one_folder_find_each_other_by_bare_name(self):
        files = {
            "architecture.toml": """
                [[layer]]
                name = "benchmarks"
                paths = ["speech-bench/tts.py"]
                [[layer]]
                name = "commands"
                paths = ["speech-bench"]
                may_use = ["benchmarks"]
                """,
            "speech-bench/bench.py": "import tts\n",
            "speech-bench/tts.py": "from bench import LANGUAGES\nimport json\n",
            # In a package a bare name is not the neighbour: that takes a relative import.
            "pkg/__init__.py": "",
            "pkg/tts.py": "import bench\n",
            "pkg/bench.py": "x = 1\n",
        }
        self.assertEqual(found(tree(files)), {("layer", "speech-bench/tts.py", "speech-bench/bench.py")})

    def test_a_source_root_that_is_not_the_repository_root(self):
        root = tree(
            {
                "python/pkg/__init__.py": "",
                "python/pkg/core.py": "from pkg import shell\n",
                "python/pkg/shell.py": "",
                "architecture.toml": '[[layer]]\nname = "core"\npaths = ["python/pkg/core.py"]\n[[layer]]\nname = "shell"\npaths = ["python/pkg/shell.py"]\n',
            }
        )
        self.assertEqual(found(root), {("layer", "python/pkg/core.py", "python/pkg/shell.py")})


class JavaScript(unittest.TestCase):
    def test_imports_aliases_and_effects(self):
        root = tree(
            {
                "src/core/sum.ts": """
                    import { fmt } from "../ui/format.js";
                    import fs from "node:fs";
                    // import x from "../ui/ignored";
                    export const now = () => Date.now();
                    """,
                "src/core/ok.ts": 'import { z } from "zod";\nexport const a = 1;\n',
                "src/ui/format.ts": 'import { now } from "@/core/sum";\nexport * from "./index";\nconsole.log(1);\n',
                "src/ui/index.ts": "export const b = 2;\n",
                "src/core/sum.test.ts": 'import fs from "fs";\n',
                "architecture.toml": """
                    [[layer]]
                    name = "core"
                    paths = ["src/core"]
                    pure = true
                    [[layer]]
                    name = "ui"
                    paths = ["src/ui"]
                    may_use = ["core"]
                    [javascript.aliases]
                    "@/" = "src/"
                    """,
            }
        )
        self.assertEqual(
            found(root),
            {
                ("layer", "src/core/sum.ts", "src/ui/format.ts"),
                ("purity", "src/core/sum.ts", "fs"),
                ("purity", "src/core/sum.ts", "Date.now()"),
            },
        )


class Cpp(unittest.TestCase):
    def test_includes(self):
        root = tree(
            {
                "core/sum.h": '#include "sum_impl.h"\n#include <vector>\n',
                "core/sum_impl.h": '#include "ui/window.h"\n#include <fstream>\n#include <QtNetwork/QNetworkReply>\n',
                "ui/window.h": '#include "core/sum.h"\n#include <QFile>\n',
                "architecture.toml": '[[layer]]\nname = "core"\npaths = ["core"]\npure = true\n[[layer]]\nname = "ui"\npaths = ["ui"]\nmay_use = ["core"]\n',
            }
        )
        self.assertEqual(
            found(root),
            {
                ("layer", "core/sum_impl.h", "ui/window.h"),
                ("purity", "core/sum_impl.h", "fstream"),
                ("purity", "core/sum_impl.h", "QtNetwork"),
            },
        )


class Unreadable(unittest.TestCase):
    def test_a_file_that_does_not_parse_fails_instead_of_passing_unchecked(self):
        files = dict(Python.FILES)
        files["app/core/broken.py"] = "def f(:\n"
        files["notes/broken.py"] = "def f(:\n"
        self.assertEqual(found(tree(files)), {("unreadable", "app/core/broken.py", "-")})


class Strict(unittest.TestCase):
    def test_strict_reports_files_in_no_layer(self):
        files = dict(Python.FILES)
        files["architecture.toml"] = "strict = true\n" + textwrap.dedent(files["architecture.toml"])
        files["app/loose.py"] = "x = 1\n"
        self.assertEqual(found(tree(files)), {("unassigned", "app/__init__.py", "-"), ("unassigned", "app/loose.py", "-")})


class Baseline(unittest.TestCase):
    def setUp(self):
        files = dict(Python.FILES)
        files["app/core/plan.py"] += "\n            import subprocess\n"
        self.root = tree(files)
        self.path = os.path.join(self.root, cli.BASELINE)

    def add(self, name: str, text: str) -> None:
        with open(os.path.join(self.root, name), "a", encoding="utf-8") as handle:
            handle.write(text)

    def test_known_violations_pass_new_ones_fail(self):
        self.assertEqual(run(self.root)[0], 1)
        self.assertEqual(run(self.root, "--accept")[0], 0)
        self.assertEqual(run(self.root)[0], 0)
        self.add("app/core/plan.py", "import socket\n")
        code, out = run(self.root)
        self.assertEqual(code, 1)
        self.assertIn("app/core/plan.py:7: purity:", out)
        self.assertIn("1 new violations", out)
        self.assertNotIn("subprocess", out)

    def test_a_fixed_violation_must_leave_the_baseline(self):
        run(self.root, "--accept")
        with open(os.path.join(self.root, "app/core/plan.py"), encoding="utf-8") as handle:
            text = handle.read().replace("import subprocess\n", "")
        with open(os.path.join(self.root, "app/core/plan.py"), "w", encoding="utf-8") as handle:
            handle.write(text)
        code, out = run(self.root)
        self.assertEqual(code, 1)
        self.assertIn("1 baseline entries no longer occur", out)
        self.assertEqual(run(self.root, "--prune")[0], 0)
        self.assertEqual(baseline.load(self.path), set())
        self.assertEqual(run(self.root)[0], 0)

    def test_the_file_is_sorted_one_entry_per_line(self):
        keys = {("purity", "b.py", "os"), ("layer", "a.py", "c.py")}
        text = baseline.dump(keys)
        self.assertEqual(baseline.parse(text), keys)
        self.assertEqual([line.strip()[:20] for line in text.splitlines()[3:5]], ['{"rule": "layer", "f', '{"rule": "purity", "'])
        self.assertEqual(baseline.parse(baseline.dump(set())), set())
        # Two spaces a level, as an .editorconfig usually asks of JSON.
        self.assertTrue(all((len(line) - len(line.lstrip())) % 2 == 0 for line in text.splitlines()))

    def test_since_refuses_a_baseline_that_grew(self):
        def git(*args: str) -> None:
            subprocess.run(
                ["git", "-C", self.root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
                check=True,
                capture_output=True,
            )

        git("init", "-q", "-b", "main")
        git("add", "-A")
        git("commit", "-q", "-m", "before the rules had a baseline")
        # The rules exist at HEAD but no baseline does, so every entry counts as added.
        run(self.root, "--accept")
        code, out = run(self.root, "--since", "HEAD")
        self.assertEqual(code, 1)
        self.assertIn("1 entries were added to the baseline", out)
        git("add", "-A")
        git("commit", "-q", "-m", "baseline")
        self.assertEqual(run(self.root, "--since", "HEAD")[0], 0)
        self.assertEqual(run(self.root, "--since", "no-such-revision")[0], 2)


class Walk(unittest.TestCase):
    def test_what_gitignore_leaves_out_is_not_read(self):
        files = dict(Python.FILES)
        files["scratch/copy.py"] = "from app.adapters import disk\n"
        files["architecture.toml"] = textwrap.dedent(files["architecture.toml"]).replace('"app/core"', '"app/core", "scratch"')
        root = tree(files)
        self.assertEqual(found(root), {("layer", "scratch/copy.py", "app/adapters/disk.py")})
        subprocess.run(["git", "-C", root, "init", "-q"], check=True, capture_output=True)
        self.assertEqual(found(root), {("layer", "scratch/copy.py", "app/adapters/disk.py")})
        with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as handle:
            handle.write("scratch/\n")
        self.assertEqual(found(root), set())


class CommandLine(unittest.TestCase):
    def test_without_a_mode_it_checks(self):
        self.assertEqual(call("--root", tree(Python.FILES)), call("--check", "--root", tree(Python.FILES)))
        files = dict(Python.FILES)
        files["app/core/plan.py"] += "\n            import subprocess\n"
        self.assertEqual(call("--root", tree(files))[0], 1)

    def test_two_modes_are_refused(self):
        self.assertEqual(call("--check", "--accept")[0], 2)

    def test_no_rules_is_a_skip_not_a_failure(self):
        code, out = run(tree({"a.py": ""}))
        self.assertEqual(code, 0)
        self.assertIn("skipping layers", out)

    def test_a_broken_config_exits_2(self):
        self.assertEqual(run(tree({"architecture.toml": "version = 9\n"}))[0], 2)
        self.assertEqual(run(tree({"a.py": ""}), "--config", "/nonexistent/architecture.toml")[0], 2)

    def test_explain_lists_layers(self):
        code, out = run(tree(Python.FILES), "--explain")
        self.assertEqual(code, 0)
        self.assertIn("core (pure, may use: nothing): 3 files", out)
        self.assertIn("in no layer: 1 files", out)
        code, out = run(tree(Python.FILES), "--explain", "--format", "json")
        self.assertEqual([layer["name"] for layer in json.loads(out)["layers"]], ["core", "adapters"])


class Effects(unittest.TestCase):
    def test_an_entry_covers_itself_and_what_is_below_it(self):
        self.assertTrue(covers("std::fs", "std", "std::fs::read"))
        self.assertTrue(covers("os", "os", "os.environ"))
        self.assertFalse(covers("std::fs", "std", "std::fsx"))
        self.assertFalse(covers("os", "ostrich", "ostrich"))


if __name__ == "__main__":
    unittest.main()
