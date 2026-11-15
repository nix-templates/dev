"""Tests for ci. Run with: PYTHONPATH=.:../layers:../../mcp python -m unittest discover -s tests

nix is a stand-in here: it hands out the script of a dev shell, and the dev
shell is a directory of commands written with the library's own helpers.
"""

import os
import tempfile
import unittest

from support import Nix, checkout, ci, git, shell

from ci import environment, watch
from ci.cli import option, rules, short

# The five commands of a project that is in order, as mkProject writes them.
CLEAN = {
    "quality": 'part shell\nrun true\npart_end\nchecked quality\nexit "$status"\n',
    "style": 'echo "style got: $*"\npart shell\nrun true\npart_end\nchecked style\nexit "$status"\n',
    "security": 'run true\nchecked security\nexit "$status"\n',
    "architecture": 'echo ":: architecture${*:+ $*}"\necho "architecture: ok (3 files checked, 3 of them in a layer, 0 known violations in the baseline)"\nexit "$status"\n',
    "tests": 'echo ":: tests: run"\npart shell\nrun true\nchecked tests\nexit "$status"\n',
}

RULES = '[[layer]]\nname = "all"\npaths = ["."]\n'


def plain(files: dict[str, str] | None = None, **commands: str) -> tuple[str, Nix]:
    """A checkout without a flake, and a nix that composes a dev shell with these commands."""
    nix = Nix()
    nix.answer("composed", shell({**CLEAN, **commands}))
    return checkout(files or {"run.sh": "echo 1\n"}), nix


def flaked(script: str | None, files: dict[str, str] | None = None) -> tuple[str, Nix]:
    """A checkout with a flake, and a nix for which its default dev shell is this script."""
    nix = Nix()
    nix.answer("eval", "true\n" if script is not None else "false\n")
    nix.answer("own", script)
    nix.answer("composed", shell(CLEAN))
    return checkout({"flake.nix": "{ }\n", "flake.lock": "{ }\n", "run.sh": "echo 1\n", **(files or {})}), nix


class Composed(unittest.TestCase):
    def test_a_checkout_without_a_flake_gets_a_dev_shell_for_its_languages(self):
        root, nix = plain({"run.sh": "echo 1\n", "app.py": "print(1)\n"})
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(
            result.said[:2],
            [
                "ci: quality in a dev shell made for python, shell by nix-templates/dev 0123456789ab with nixpkgs fedcba987654",
                "ci: languages found: python (1 file), shell (1 file)",
            ],
        )
        self.assertEqual(result.out, ":: true\n")
        (call,) = nix.calls
        self.assertIn("print-dev-env --file /toolbox/lib/ci/compose.nix", call)
        self.assertIn('--argstr nixpkgs /nixpkgs --argstr system x86_64-linux --arg languages [ "python" "shell" ]', call)

    def test_the_first_line_of_its_own_names_the_environment_before_nix_says_anything(self):
        root, nix = plain()
        nix.answer("composed", None)
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 2)
        lines = result.err.splitlines()
        self.assertTrue(lines[0].startswith("ci: quality in a dev shell made for shell by nix-templates/dev"), lines)
        self.assertLess(lines.index("ci: languages found: shell (1 file)"), lines.index("error: nix has no answer for composed"))
        self.assertTrue(lines[-1].startswith("ci: quality could not run: no environment could be made for these languages"), lines)

    def test_no_language_is_said_and_still_runs_what_every_project_gets(self):
        root, nix = plain({"LICENSE": "All rights reserved.\n"})
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertTrue(result.said[0].startswith("ci: quality in a dev shell made for no language by"), result.said)
        self.assertIn("ci: checked nothing (no-languages): no language of nix-templates/dev was found in this checkout, so only what every project gets ran", result.said)
        self.assertIn("--arg languages [  ]", nix.calls[0])

    def test_nothing_of_the_checkout_is_written(self):
        root, nix = plain()
        before = git(root, "status", "--porcelain", "--ignored")
        for command in ("quality", "style", "security", "tests"):
            ci(root, command, nix=nix)
        self.assertEqual(git(root, "status", "--porcelain", "--ignored"), before)


class Kept(unittest.TestCase):
    def test_nix_is_asked_once_for_the_five_commands_of_a_pipeline(self):
        root, nix = plain({"run.sh": "echo 1\n", "architecture.toml": RULES})
        cache = tempfile.mkdtemp()
        for command in ("quality", "style", "security", "architecture", "tests"):
            self.assertEqual(ci(root, command, nix=nix, cache=cache).code, 0, command)
        self.assertEqual(len(nix.calls), 1)

    def test_other_languages_are_another_dev_shell(self):
        root, nix = plain()
        cache = tempfile.mkdtemp()
        ci(root, "quality", nix=nix, cache=cache)
        other = checkout({"app.py": "print(1)\n"})
        ci(other, "quality", nix=nix, cache=cache)
        self.assertEqual(len(nix.calls), 2)

    def test_without_a_cache_directory_nix_is_asked_every_time(self):
        root, nix = plain()
        blocked = os.path.join(tempfile.mkdtemp(), "a-file")
        with open(blocked, "w", encoding="utf-8") as handle:
            handle.write("in the way\n")
        for _ in range(2):
            self.assertEqual(ci(root, "quality", nix=nix, cache=blocked).code, 0)
        self.assertEqual(len(nix.calls), 2)

    def test_a_kept_shell_whose_store_paths_are_gone_is_asked_for_again(self):
        root, nix = plain()
        cache = tempfile.mkdtemp()
        good = shell(CLEAN)
        nix.answer("composed", 'export PATH="/nix/store/00000000000000000000000000000000-collected/bin:$PATH"\n' + good)
        result = ci(root, "quality", nix=nix, cache=cache)
        self.assertEqual(result.code, 2)
        self.assertIn("ci: quality could not run: the dev shell names store paths that are not there", result.said)
        self.assertEqual(len(nix.calls), 2)
        nix.answer("composed", good)
        self.assertEqual(ci(root, "quality", nix=nix, cache=cache).code, 0)
        self.assertEqual(len(nix.calls), 3)

    def test_the_own_dev_shell_is_kept_by_commit_and_not_when_files_differ_from_it(self):
        root, nix = flaked(shell(CLEAN))
        cache = tempfile.mkdtemp()
        for _ in range(2):
            self.assertEqual(ci(root, "quality", nix=nix, cache=cache).code, 0)
        self.assertEqual((nix.asked("eval"), nix.asked("print-dev-env")), (1, 1))
        with open(os.path.join(root, "run.sh"), "a", encoding="utf-8") as handle:
            handle.write("echo 2\n")
        for _ in range(2):
            self.assertEqual(ci(root, "quality", nix=nix, cache=cache).code, 0)
        self.assertEqual((nix.asked("eval"), nix.asked("print-dev-env")), (3, 3))
        git(root, "commit", "-qam", "more")
        for _ in range(2):
            self.assertEqual(ci(root, "quality", nix=nix, cache=cache).code, 0)
        self.assertEqual((nix.asked("eval"), nix.asked("print-dev-env")), (4, 4))

    def test_a_flake_without_a_lock_file_is_never_kept(self):
        root, nix = flaked(shell(CLEAN))
        git(root, "rm", "-q", "flake.lock")
        git(root, "commit", "-qm", "no lock")
        cache = tempfile.mkdtemp()
        for _ in range(2):
            self.assertEqual(ci(root, "quality", nix=nix, cache=cache).code, 0)
        self.assertEqual(nix.asked("print-dev-env"), 2)


class Own(unittest.TestCase):
    def test_a_flake_whose_dev_shell_has_the_command_runs_it_there(self):
        root, nix = flaked(shell({"quality": 'run echo "from the project"\nexit "$status"\n'}))
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.said, ["ci: quality in this checkout's own dev shell (nix-templates/dev, at a revision its flake.lock does not name)"])
        self.assertEqual(result.out, ":: echo from the project\nfrom the project\n")
        self.assertEqual(nix.asked("print-dev-env --file"), 0)
        self.assertIn(f"print-dev-env --no-write-lock-file {root}#devShells.x86_64-linux.default", nix.calls[-1])

    def test_the_first_line_names_the_pin_that_flake_lock_has(self):
        lock = '{"nodes": {"dev": {"locked": {"type": "github", "owner": "nix-templates", "repo": "dev", "rev": "4c1d329e9187646be557f240c0f0f364b5ef5b96"}}}}\n'
        root, nix = flaked(shell(CLEAN), {"flake.lock": lock})
        self.assertEqual(ci(root, "quality", nix=nix).said[0], "ci: quality in this checkout's own dev shell (nix-templates/dev 4c1d329e9187)")

    def test_what_the_shell_prints_while_it_is_set_up_comes_after_the_first_line(self):
        root, nix = flaked(shell(CLEAN, hook='echo "welcome to the shell"; echo "and its errors" >&2'))
        result = ci(root, "quality", nix=nix)
        lines = result.err.splitlines()
        self.assertTrue(lines[0].startswith("ci: quality in this checkout's own dev shell"), lines)
        self.assertEqual(lines[1:3], ["welcome to the shell", "and its errors"])
        self.assertEqual(result.out, ":: true\n")

    def test_a_flake_without_a_default_dev_shell_gets_one_made(self):
        root, nix = flaked(None)
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertTrue(result.said[0].startswith("ci: quality in a dev shell made for nix, shell by"), result.said)
        self.assertEqual(result.said[1], "ci: this checkout's flake has no default dev shell, so one was made here")
        self.assertEqual(nix.asked("print-dev-env --no-write-lock-file"), 0)

    def test_a_dev_shell_without_the_command_gets_one_made(self):
        root, nix = flaked(shell({"quality": CLEAN["quality"]}))
        result = ci(root, "tests", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertTrue(result.said[0].startswith("ci: tests in a dev shell made for nix, shell by"), result.said)
        self.assertEqual(result.said[1], "ci: the dev shell of this checkout's flake has no tests, so one was made here")
        self.assertEqual(result.out, ":: tests: run\n:: true\n")

    def test_a_command_outside_the_dev_shell_is_not_the_projects(self):
        elsewhere = shell({"quality": 'echo "from outside"\n'}, own=("quality",)).split('"')[1].split("$")[0]
        root, nix = flaked(shell({"style": CLEAN["style"]}))
        result = ci(root, "quality", nix=nix, path=os.pathsep.join([nix.directory, elsewhere, os.environ["PATH"]]))
        self.assertEqual(result.out, ":: true\n")
        self.assertIn("ci: the dev shell of this checkout's flake has no quality, so one was made here", result.said)

    def test_the_fmt_of_coreutils_is_no_command(self):
        entered = environment.Entered({}, [], "")
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "fmt"), "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\n")
            os.chmod(os.path.join(directory, "fmt"), 0o755)
            entered.path = [directory]
            self.assertEqual(entered.command("fmt"), os.path.join(directory, "fmt"))
            self.assertIsNone(entered.command("style"))
        self.assertTrue(environment.stands_in("/nix/store/5s3xgrhk7yk3bwlzvlkycdj0k9nqjnya-coreutils-9.8/bin/fmt"))
        self.assertTrue(environment.stands_in("/nix/store/5s3xgrhk7yk3bwlzvlkycdj0k9nqjnya-busybox-1.36.1/bin/fmt"))
        self.assertFalse(environment.stands_in("/nix/store/085d7jfp4fhvax2r465ryi6879j8jq66-fmt/bin/fmt"))
        self.assertFalse(environment.stands_in("/home/someone/project/bin/fmt"))

    def test_a_flake_that_does_not_evaluate_is_not_replaced_by_a_made_shell(self):
        root, nix = flaked(shell(CLEAN))
        nix.answer("eval", None)
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 2)
        self.assertEqual(result.said, ["ci: quality could not run: this checkout's flake.nix could not be read (nix ended with status 1; what it said is above)"])
        self.assertIn("error: nix has no answer for eval", result.err)
        self.assertEqual(result.out, "")

    def test_a_dev_shell_that_does_not_build_is_not_replaced_either(self):
        root, nix = flaked(shell(CLEAN))
        nix.answer("own", None)
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 2)
        self.assertTrue(result.said[-1].startswith("ci: quality could not run: the dev shell of this checkout's flake could not be made"), result.said)
        self.assertEqual(nix.asked("print-dev-env --file"), 0)

    def test_a_dev_shell_that_stops_while_it_is_set_up_cannot_run(self):
        root, nix = flaked('echo "missing a secret"; exit 3\n')
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 2)
        self.assertIn("ci: quality could not run: the dev shell could not be entered, it said:", result.said)
        self.assertIn("missing a secret", result.err)

    def test_the_directory_a_dev_shell_makes_for_itself_is_removed(self):
        made = os.path.join(tempfile.mkdtemp(), "nix-shell.kept")
        root, nix = flaked(f'mkdir -p "{made}"\nexport NIX_BUILD_TOP="{made}"\n' + shell(CLEAN))
        self.assertEqual(ci(root, "quality", nix=nix).code, 0)
        self.assertFalse(os.path.exists(made))

    def test_a_projects_own_program_runs_and_is_said_to_be_one(self):
        root, nix = flaked(shell({"quality": 'echo "all fine"\n'}, own=("quality",)))
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(
            result.said,
            [
                "ci: quality in this checkout's own dev shell (its own quality, not the one of nix-templates/dev)",
                "ci: checked nothing (own-command): quality is this project's own program, so what it checked is not known",
            ],
        )


class Machine(unittest.TestCase):
    def test_without_nix_it_cannot_run(self):
        root, _ = plain()
        tools = tempfile.mkdtemp()
        for name in ("git", "bash", "env"):
            os.symlink(next(os.path.join(d, name) for d in os.environ["PATH"].split(os.pathsep) if os.path.exists(os.path.join(d, name))), os.path.join(tools, name))
        result = ci(root, "quality", path=tools)
        self.assertEqual(result.code, 2)
        self.assertEqual(result.said[-1], "ci: quality could not run: there is no nix on PATH")


class Commands(unittest.TestCase):
    def test_fmt_is_fmt_check(self):
        root, nix = plain()
        self.assertIn("style got: --check\n", ci(root, "style", nix=nix).out)
        self.assertIn("style got: --check\n", ci(root, "style", "--check", nix=nix).out)

    def test_arguments_go_to_the_command_as_they_are(self):
        root, nix = plain(
            {"run.sh": "echo 1\n", "architecture.toml": RULES},
            architecture='echo "architecture got: $# arguments:"; printf "<%s>\\n" "$@"\n',
            tests='echo "tests got: $*"\n',
        )
        self.assertEqual(ci(root, "architecture", "--since", "main", "--format=json", "a b", nix=nix).out, "architecture got: 4 arguments:\n<--since>\n<main>\n<--format=json>\n<a b>\n")
        self.assertEqual(ci(root, "tests", "--coverage", nix=nix).out, "tests got: --coverage\n")

    def test_what_the_command_prints_stays_on_stdout_and_ci_on_stderr(self):
        root, nix = plain(quality='echo "to stdout"; echo "to stderr" >&2; run true\n')
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.out, "to stdout\n:: true\n")
        self.assertIn("to stderr", result.err)
        self.assertNotIn("ci: ", result.out)

    def test_the_exit_code_is_passed_found_or_could_not_run(self):
        for status, code, note in (
            (0, 0, None),
            (1, 1, None),
            (2, 2, None),
            (3, 1, "ci: quality ended with status 3, which counts as found something"),
            (127, 2, "ci: quality ended with status 127, which counts as could not run"),
        ):
            with self.subTest(status=status):
                root, nix = plain(quality=f"run true\nexit {status}\n")
                result = ci(root, "quality", nix=nix)
                self.assertEqual(result.code, code)
                self.assertEqual(result.said[2:], [note] if note else [])

    def test_a_command_that_is_killed_could_not_run(self):
        root, nix = plain(quality='run true\nkill -KILL "$$"\n')
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 2)
        self.assertEqual(result.said[-1], "ci: quality ended with status -9, which counts as could not run")

    def test_a_tool_that_fails_is_a_finding(self):
        root, nix = plain(quality='part shell\nrun false\npart_end\nrun true\nchecked quality\nexit "$status"\n')
        result = ci(root, "quality", nix=nix)
        self.assertEqual((result.code, result.out), (1, ":: false\n:: true\n"))

    def test_only_the_five_commands_exist(self):
        root, nix = plain()
        for arguments, said in (((), "ci: which command?"), (("build",), "ci: there is no command build"), (("--fast", "quality"), "ci: there is no option --fast")):
            result = ci(root, *arguments, nix=nix)
            self.assertEqual((result.code, result.said[0]), (2, said))
            self.assertIn("usage: ci [--strict[=CASE,...]] <style|security|quality|architecture|tests> [arguments]", result.err)
        self.assertEqual(nix.calls, [])

    def test_help_and_version_and_languages(self):
        root, nix = plain({"run.sh": "echo 1\n", "lib/more.sh": "echo 2\n", "app.py": "print(1)\n"})
        self.assertIn("usage: ci", ci(root, "--help", nix=nix).out)
        self.assertEqual(ci(root, "--version", nix=nix).out, "ci 0.1.0 of nix-templates/dev 0123456789abcdef0123456789abcdef01234567\n")
        self.assertEqual(ci(root, "--languages", nix=nix).out, "python: 1 file, such as app.py\nshell: 2 files, such as lib/more.sh\n")
        self.assertEqual(nix.calls, [])


class Layers(unittest.TestCase):
    def test_without_architecture_toml_it_fails_with_one_line_and_builds_nothing(self):
        root, nix = plain()
        result = ci(root, "architecture", nix=nix)
        self.assertEqual(result.code, 1)
        self.assertEqual(
            result.err,
            "ci: architecture: there is no architecture.toml in this checkout, so nothing was checked. Add one that names the layers and "
            'what each may use. A project with nothing to keep apart says so with one layer: paths = ["."].\n',
        )
        self.assertEqual((result.out, nix.calls), ("", []))

    def test_the_same_holds_with_a_flake_of_its_own(self):
        root, nix = flaked(shell(CLEAN))
        result = ci(root, "architecture", nix=nix)
        self.assertEqual((result.code, nix.calls), (1, []))
        self.assertTrue(result.err.startswith("ci: architecture: there is no architecture.toml in this checkout"), result.err)

    def test_with_one_it_runs(self):
        root, nix = plain({"run.sh": "echo 1\n", "architecture.toml": RULES})
        result = ci(root, "architecture", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(len(result.said), 2)

    def test_the_file_is_looked_for_where_layers_would(self):
        self.assertEqual(rules([])[0], "architecture.toml")
        self.assertEqual(rules(["--root", "missing"])[0], "missing/architecture.toml")
        self.assertEqual(rules(["--root=missing"])[0], "missing/architecture.toml")
        # The command itself says that a file named with --config does not exist, and it lists its languages without one.
        self.assertEqual(rules(["--config", "missing.toml"]), (None, None))
        self.assertEqual(rules(["--languages"]), (None, None))

    def test_no_file_in_a_layer_is_said(self):
        root, nix = plain(
            {"run.sh": "echo 1\n", "architecture.toml": RULES},
            architecture='echo "architecture: ok (3 files checked, 0 of them in a layer, 0 known violations in the baseline)"\n',
        )
        result = ci(root, "architecture", nix=nix)
        self.assertEqual(result.code, 0)
        self.assertEqual(result.said[-1], "ci: checked nothing (no-layer-files): architecture read 3 files and architecture.toml puts none of them in a layer")

    def test_a_checkout_with_nothing_for_layers_to_read_has_said_so_with_its_rules(self):
        root, nix = plain(
            {"README.md": "# Words\n", "architecture.toml": RULES},
            architecture='echo "architecture: ok (0 files checked, 0 of them in a layer, 0 known violations in the baseline)"\n',
        )
        result = ci(root, "--strict", "architecture", nix=nix)
        self.assertEqual((result.code, len(result.said)), (0, 2))

    def test_a_revision_without_rules_compares_nothing(self):
        root, nix = plain()
        with open(os.path.join(root, "architecture.toml"), "w", encoding="utf-8") as handle:
            handle.write(RULES)
        git(root, "add", "-A")
        git(root, "commit", "-qm", "rules")
        result = ci(root, "architecture", "--since", "HEAD~1", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.said[-1], "ci: checked nothing (no-comparison): HEAD~1 has no architecture.toml, so --since compared nothing")
        self.assertEqual(len(ci(root, "architecture", "--since=HEAD", nix=nix).said), 2)
        # A revision that does not exist is for the command to refuse.
        self.assertEqual(len(ci(root, "architecture", "--since", "no-such-branch", nix=nix).said), 2)


class CheckedNothing(unittest.TestCase):
    def test_a_command_that_ran_no_tool_is_said(self):
        root, nix = plain(style='checked style\nexit "$status"\n')
        result = ci(root, "style", nix=nix)
        self.assertEqual(result.code, 0)
        self.assertEqual(result.out, ":: checked nothing: style ran no tool\n")
        self.assertEqual(result.said[2:], ["ci: checked nothing (no-tool): style ran no tool"])

    def test_the_commands_of_an_older_revision_are_counted_too(self):
        root, nix = plain(tests='echo ":: tests: run"\necho ":: skipping bats (no *.bats files)"\nexit "$status"\n')
        result = ci(root, "tests", nix=nix)
        self.assertEqual(result.said[2:], ["ci: checked nothing (no-tool): tests ran no tool"])

    def test_a_language_whose_part_ran_nothing_is_named(self):
        body = """
            echo ":: tests: run"
            part shell
            run_on '*.bats' true
            part python
            when no-such-file true
            part python go
            when no-such-file true
            part go
            run true
            checked tests
            exit "$status"
            """
        root, nix = plain({"run.sh": "echo 1\n", "tests/run.bats": "@test x { true; }\n"}, tests=body)
        result = ci(root, "tests", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertIn(":: checked nothing: tests for python\n", result.out)
        self.assertNotIn("for shell", result.out)
        self.assertNotIn("for go", result.out)
        self.assertEqual(result.said[2:], ["ci: checked nothing (language): tests ran nothing for python"])

    def test_a_tool_that_found_nothing_to_check_did_not_run_and_did_not_fail(self):
        # pytest ends with 5 when it collected no test.
        body = """
            echo ":: tests: run"
            part python
            run_some 5 sh -c 'echo "no tests ran"; exit 5'
            part shell
            run true
            checked tests
            exit "$status"
            """
        root, nix = plain(tests=body)
        result = ci(root, "tests", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertIn(":: skipping sh -c echo \"no tests ran\"; exit 5 (it found nothing to check)\n", result.out)
        self.assertEqual(result.said[2:], ["ci: checked nothing (language): tests ran nothing for python"])

    def test_when_that_was_the_only_tool_the_command_ran_none(self):
        root, nix = plain(tests='echo ":: tests: run"\npart python\nrun_some 5 sh -c "exit 5"\nchecked tests\nexit "$status"\n')
        result = ci(root, "tests", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.said[2:], ["ci: checked nothing (no-tool): tests ran no tool", "ci: checked nothing (language): tests ran nothing for python"])

    def test_such_a_tool_still_fails_and_still_counts_with_any_other_status(self):
        for status, code, lines in ((1, 1, 2), (0, 0, 2)):
            root, nix = plain(tests=f'echo ":: tests: run"\npart python\nrun_some 5 sh -c "exit {status}"\nchecked tests\nexit "$status"\n')
            result = ci(root, "tests", nix=nix)
            self.assertEqual((result.code, len(result.said)), (code, lines), result.err)

    def test_what_runs_for_every_project_is_no_languages_part(self):
        root, nix = plain(quality='part shell\nwhen no-such-file true\npart_end\nrun true\nchecked quality\nexit "$status"\n')
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.out, ":: skipping true (no no-such-file here)\n:: true\n:: checked nothing: quality for shell\n")
        self.assertEqual(result.said[2:], ["ci: checked nothing (language): quality ran nothing for shell"])

    def test_strict_fails_a_run_that_checked_nothing(self):
        root, nix = plain(style='checked style\nexit "$status"\n')
        result = ci(root, "--strict", "style", nix=nix)
        self.assertEqual(result.code, 1)
        self.assertEqual(result.said[-2:], ["ci: checked nothing (no-tool): style ran no tool", "ci: failing: --strict was given for no-tool"])
        self.assertEqual(ci(root, "--strict", "quality", nix=nix).code, 0)

    def test_strict_can_name_its_cases(self):
        root, nix = plain(style='checked style\nexit "$status"\n')
        self.assertEqual(ci(root, "--strict=language,no-languages", "style", nix=nix).code, 0)
        self.assertEqual(ci(root, "--strict=language,no-tool", "style", nix=nix).code, 1)
        result = ci(root, "--strict=no-tests", "style", nix=nix)
        self.assertEqual(result.code, 2)
        self.assertEqual(result.said, [f"ci: --strict takes these cases: {', '.join(watch.CASES)} (not no-tests)"])

    def test_strict_leaves_a_failure_as_it_is(self):
        root, nix = plain(style="exit 2\n")
        self.assertEqual(ci(root, "--strict", "style", nix=nix).code, 2)


class Scripts(unittest.TestCase):
    """The helpers that find a script with no extension by its first line."""

    FILES = {
        "bin/tool": "#!/usr/bin/env python3\nprint(1)\n",
        "bin/older": "#!/usr/bin/python3.12 -u\nprint(1)\n",
        "bin/report": "#!/usr/bin/perl\nprint 1;\n",
        "bin/start": "#!/usr/bin/env bash\necho 1\n",
        "bin/notes": "python and perl are words here\n",
        "lib/module.py": "#!/usr/bin/env python3\nprint(1)\n",
        "node_modules/dep/tool": "#!/usr/bin/env python3\nprint(1)\n",
    }

    def run_lint(self, body: str, files: dict[str, str] | None = None) -> list[str]:
        root, nix = plain(files or self.FILES, quality=body)
        return sorted(ci(root, "quality", nix=nix).out.splitlines())

    def test_scripts_are_found_by_the_interpreter_their_first_line_names(self):
        self.assertEqual(self.run_lint("scripts 'python[0-9.]*'\n"), ["./bin/older", "./bin/tool"])
        self.assertEqual(self.run_lint("scripts perl\n"), ["./bin/report"])
        self.assertEqual(self.run_lint("shell_scripts\n"), ["./bin/start"])

    def test_a_command_runs_on_the_scripts_of_an_interpreter_or_says_it_skips(self):
        self.assertEqual(self.run_lint("on_scripts perl echo critic\n"), [":: echo critic ./bin/report", "critic ./bin/report"])
        self.assertEqual(self.run_lint("on_scripts ruby echo cop\n"), [":: skipping echo (no ruby scripts)"])

    def test_a_tool_that_takes_a_directory_gets_the_scripts_as_well(self):
        self.assertEqual(self.run_lint("with_scripts perl echo check .\n"), [":: echo check . ./bin/report", "check . ./bin/report"])
        self.assertEqual(self.run_lint("with_scripts ruby echo check .\n"), [":: echo check .", "check ."])


class Renamed(unittest.TestCase):
    """Four commands had other names before: lint, fmt, scan and layers. ci does not take those."""

    # The commands of a revision from before, by their old names.
    OLDER = {
        "lint": 'part shell\nrun true\npart_end\nexit "$status"\n',
        "fmt": 'echo "fmt got: $*"\nrun true\nexit "$status"\n',
        "scan": 'run true\nexit "$status"\n',
        "layers": 'echo ":: layers${*:+ $*}"\necho "layers: ok (3 files checked, 0 of them in a layer, 0 known violations in the baseline)"\nexit "$status"\n',
        "tests": 'echo ":: tests: run"\nrun true\nexit "$status"\n',
    }

    def test_an_old_name_is_no_command_and_ci_says_what_it_is_called_now(self):
        root, nix = plain({"run.sh": "echo 1\n", "architecture.toml": RULES})
        for before, now in (("lint", "quality"), ("fmt", "style"), ("scan", "security"), ("layers", "architecture")):
            with self.subTest(before=before):
                result = ci(root, before, nix=nix)
                self.assertEqual(result.code, 2)
                self.assertEqual(result.said, [f"ci: there is no command {before}. It is called {now} now"])
                self.assertIn("usage: ci [--strict[=CASE,...]] <style|security|quality|architecture|tests> [arguments]", result.err)
                self.assertEqual(result.out, "")
        self.assertEqual(nix.calls, [])

    def test_a_checkout_that_pins_a_revision_from_before_is_served_by_the_commands_it_has(self):
        # Its pin decides its tools, and at that pin the commands have their old names.
        root, nix = flaked(shell(self.OLDER), {"architecture.toml": RULES})
        result = ci(root, "quality", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(
            result.said,
            ["ci: quality in this checkout's own dev shell (nix-templates/dev, at a revision its flake.lock does not name, where it is still called lint)"],
        )
        self.assertEqual(result.out, ":: true\n")
        self.assertIn("fmt got: --check\n", ci(root, "style", nix=nix).out)
        self.assertEqual(ci(root, "security", nix=nix).out, ":: true\n")
        self.assertEqual(nix.asked("print-dev-env --file"), 0)

    def test_what_such_a_shell_prints_is_still_understood(self):
        root, nix = flaked(shell(self.OLDER), {"architecture.toml": RULES})
        result = ci(root, "architecture", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.said[-1], "ci: checked nothing (no-layer-files): architecture read 3 files and architecture.toml puts none of them in a layer")

    def test_a_dev_shell_with_both_names_runs_the_new_one(self):
        both = {**CLEAN, "lint": 'echo "the old name was used"\nexit 3\n'}
        root, nix = flaked(shell(both))
        result = ci(root, "quality", nix=nix)
        self.assertEqual((result.code, result.out), (0, ":: true\n"))
        self.assertEqual(result.said, ["ci: quality in this checkout's own dev shell (nix-templates/dev, at a revision its flake.lock does not name)"])

    def test_the_fmt_that_every_dev_shell_has_is_not_taken_for_style(self):
        # A flake that has nothing to do with this library: its shell has no style, and no fmt but the one of coreutils.
        root, nix = flaked(shell({"build": "exit 0\n"}, own=("build",)))
        result = ci(root, "style", nix=nix)
        self.assertEqual(result.code, 0, result.err)
        self.assertIn("ci: the dev shell of this checkout's flake has no style, so one was made here", result.said)


class Reading(unittest.TestCase):
    def test_tools_are_counted_and_headers_and_skips_are_not(self):
        seen = watch.Seen()
        for line in (
            ":: tests: run",
            ":: architecture --since main",
            ":: layers --since main",
            ":: skipping bats (no *.bats files)",
            ":: checked nothing: tests for go",
            "1..1",
            ":: bats a.bats",
            ":: layers-tool x",
        ):
            seen.line(line)
        self.assertEqual((seen.tools, seen.none, seen.languages, seen.read, seen.placed), (2, False, ["go"], None, None))
        seen.line(":: checked nothing: tests ran no tool")
        self.assertEqual((seen.tools, seen.none), (2, True))

    def test_the_summary_of_architecture_tells_how_many_files_are_in_a_layer(self):
        for line, numbers in (
            ("architecture: ok (12 files checked, 0 of them in a layer, 0 known violations in the baseline)", (12, 0)),
            ("architecture: FAIL: 1 new violations (12 files checked, 7 of them in a layer, 0 known violations in the baseline)", (12, 7)),
            # As a revision from before the command was renamed prints it.
            ("layers: ok (12 files checked, 0 of them in a layer, 0 known violations in the baseline)", (12, 0)),
            ("layers: FAIL: 1 new violations (12 files checked, 7 of them in a layer, 0 known violations in the baseline)", (12, 7)),
        ):
            seen = watch.Seen()
            seen.line(line)
            self.assertEqual((seen.read, seen.placed), numbers)

    def test_a_status_becomes_one_of_three(self):
        self.assertEqual([watch.verdict(status) for status in (0, 1, 2, 3, 125, 126, 127, 137, -15)], [0, 1, 2, 1, 1, 2, 2, 2, 2])

    def test_an_option_of_a_command_is_read_in_both_spellings(self):
        self.assertEqual(option(["--since", "main"], "--since"), "main")
        self.assertEqual(option(["--since=main", "--since", "next"], "--since"), "next")
        self.assertIsNone(option(["--since"], "--since"))
        self.assertIsNone(option(["--since-then=x"], "--since"))

    def test_a_commit_is_shortened_and_anything_else_is_not(self):
        self.assertEqual(short("4c1d329e9187646be557f240c0f0f364b5ef5b96"), "4c1d329e9187")
        self.assertEqual(short("4c1d329e9187646be557f240c0f0f364b5ef5b96-dirty"), "4c1d329e9187-dirty")
        self.assertEqual(short("sha256-SH6Bji2HLJ8+ChcGzueJoFmDFfRWOoIhRVx5kKqIpxo="), "sha256-SH6Bji2HLJ8+ChcGzueJoFmDFfRWOoIhRVx5kKqIpxo=")
        self.assertEqual(short("26.11pre-git"), "26.11pre-git")


if __name__ == "__main__":
    unittest.main()
