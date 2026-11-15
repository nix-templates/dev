"""Finding a checkout's languages. Run with: PYTHONPATH=.:../layers:../../mcp python -m unittest discover -s tests"""

import unittest

from samples import NEVER, SAMPLES
from support import MARKS, REAL_MARKS, checkout

from ci import detect


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
