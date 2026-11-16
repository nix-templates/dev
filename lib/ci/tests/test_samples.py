"""The systems smoke fixtures must have a real architecture check to execute."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from layers import cli
from samples import CLEAN, write


class SystemFixtures(unittest.TestCase):
    def test_clean_samples_configure_a_check_that_reads_source(self):
        for template in CLEAN:
            with self.subTest(template=template), tempfile.TemporaryDirectory() as directory:
                written = write(template, directory)
                self.assertIn("architecture.toml", written)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(cli.main(["--root", directory]), 0)
                self.assertIn("architecture: ok", output.getvalue())
                self.assertNotIn("0 of them in a layer", output.getvalue())

    def test_existing_template_architecture_rules_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            rules = Path(directory) / "architecture.toml"
            original = '[[layer]]\nname = "existing"\npaths = ["src"]\n'
            rules.write_text(original)
            self.assertNotIn("architecture.toml", write("project", directory))
            self.assertEqual(rules.read_text(), original)
