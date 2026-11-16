import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from dvt import InitError, generate, main, write_files

REGISTRY = json.loads((Path(__file__).parents[2] / "frameworks/registry.json").read_text())
CATALOGUE = {
    "frameworks": REGISTRY,
    "languages": {p.stem: {} for p in (Path(__file__).parents[2] / "languages").glob("*.nix") if p.stem != "common"},
    "devInput": "github:nix-templates/dev/deadbeef",
}
CATALOGUE["languages"]["hashi"] = {"nixpkgsConfig": ["config.allowUnfree = true;"]}


class GeneratorTests(unittest.TestCase):
    def test_every_version_is_explicit_and_inherits_its_language(self):
        for name, profile in REGISTRY.items():
            for version in profile["versions"]:
                with self.subTest(name=name, version=version):
                    files = generate(name, CATALOGUE, version)
                    self.assertIn(f'name = "{name}"; version = "{version}";', files["flake.nix"])
                    self.assertNotIn("pythonVenv", files["flake.nix"])
                    self.assertEqual(set(files), {"flake.nix", ".envrc"})

    def test_language_fallback_and_alias(self):
        self.assertIn('languages = [ "rust" ];', generate("rust", CATALOGUE)["flake.nix"])
        self.assertIn('languages = [ "node" ];', generate("js", CATALOGUE)["flake.nix"])
        self.assertIn("config.allowUnfree = true;", generate("hashi", CATALOGUE)["flake.nix"])

    def test_unknown_and_unsupported_versions_fail(self):
        for name, version in [("djnago", None), ("django", "99.0"), ("python", "4.2")]:
            with self.subTest(name=name, version=version), self.assertRaises(InitError):
                generate(name, CATALOGUE, version)

    def test_dev_reference_is_pinned_and_nix_interpolation_is_escaped(self):
        self.assertIn('dev.url = "github:nix-templates/dev/deadbeef";', generate("python", CATALOGUE)["flake.nix"])
        self.assertIn(r'path:/tmp/\${not_code}', generate("python", CATALOGUE, dev_input="path:/tmp/${not_code}")["flake.nix"])

    def test_initialization_preserves_dependency_files_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            originals = {"pyproject.toml": b"[project]\nname='existing'\n", "uv.lock": b"keep\x00exactly", "requirements.txt": b"Django==4.2.1\n", "package.json": b'{"private":true}', "package-lock.json": b"{}"}
            for name, data in originals.items():
                (root / name).write_bytes(data)
            write_files(root, generate("django", CATALOGUE, "4.2"))
            for name, data in originals.items():
                self.assertEqual((root / name).read_bytes(), data)
            self.assertEqual({p.name for p in root.iterdir()}, {*originals, "flake.nix", ".envrc"})

    def test_conflict_preflight_does_not_partially_write(self):
        for conflict in ("flake.nix", ".envrc"):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / conflict).write_text("existing")
                with self.assertRaises(InitError):
                    write_files(root, generate("python", CATALOGUE))
                self.assertEqual([p.name for p in root.iterdir()], [conflict])
                self.assertEqual((root / conflict).read_text(), "existing")

    def test_dangling_symlink_is_a_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".envrc").symlink_to(root / "missing")
            with self.assertRaises(InitError):
                write_files(root, generate("python", CATALOGUE))
            self.assertFalse((root / "flake.nix").exists())

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["init", "django", "--framework-version", "5.2", "--directory", tmp, "--dry-run"], CATALOGUE), 0)
            self.assertIn("flake.nix", json.loads(out.getvalue()))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_list_exposes_version_coverage(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["list"], CATALOGUE), 0)
        self.assertIn("django: 4.2, 5.2, 6.0", out.getvalue())





class RealCatalogueTests(unittest.TestCase):
    def test_packaged_native_version_reader(self):
        import os

        from dvt import detect_version
        catalogue_path = os.environ.get('DVT_TEST_CATALOGUE')
        if not catalogue_path:
            self.skipTest('Nix integration provides the packaged version reader')
        catalogue = json.loads(Path(catalogue_path).read_text())
        self.assertTrue(Path(catalogue['versionReader']).is_file())
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'Gemfile.lock').write_text('GEM\n  specs:\n    rails (7.2.2)\n')
            self.assertEqual(detect_version('rails', tmp, catalogue), '7.2')

    def test_every_language_and_framework_generates_parseable_nix(self):
        import os
        import subprocess
        catalogue_path = os.environ.get('DVT_TEST_CATALOGUE')
        if not catalogue_path:
            self.skipTest('Nix integration provides the complete catalogue')
        catalogue = json.loads(Path(catalogue_path).read_text())
        cases = [(name, None) for name in catalogue['languages']]
        cases += [(name, version) for name, profile in catalogue['frameworks'].items() for version in profile['versions']]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'flake.nix'
            for name, version in cases:
                with self.subTest(name=name, version=version):
                    path.write_text(generate(name, catalogue, version)['flake.nix'])
                    result = subprocess.run(['nix-instantiate', '--parse', str(path)], capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
        coverage = catalogue['coverage']['languages']
        self.assertEqual(set(coverage), set(catalogue['languages']))
        for name, entry in coverage.items():
            self.assertTrue(entry['sources'], name)
            self.assertTrue(entry['tools'], name)


class DetectionTests(unittest.TestCase):
    def detect(self, name, files):
        from dvt import detect_version
        with tempfile.TemporaryDirectory() as tmp:
            for filename, text in files.items():
                path = Path(tmp) / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            return detect_version(name, tmp, CATALOGUE)

    def test_python_lock_selects_older_framework_without_importing_it(self):
        self.assertEqual(self.detect('django', {'uv.lock': '[[package]]\nname="django"\nversion="4.2.27"\n'}), '4.2')
        self.assertEqual(self.detect('flask', {'poetry.lock': '[[package]]\nname="flask"\nversion="3.0.3"\n'}), '3.0')

    def test_python_exact_requirements_and_installed_metadata(self):
        self.assertEqual(self.detect('django', {'requirements.txt': 'Django==5.2.9\n'}), '5.2')
        self.assertEqual(self.detect('django', {'.venv/lib/python3.12/site-packages/django-4.2.dist-info/METADATA': 'Name: Django\nVersion: 4.2.27\n'}), '4.2')

    def test_node_installed_and_lock_metadata(self):
        self.assertEqual(self.detect('nextjs', {'node_modules/next/package.json': '{"version":"14.2.35"}'}), '14')
        self.assertEqual(self.detect('vue', {'package-lock.json': '{"packages":{"node_modules/vue":{"version":"2.7.16"}}}'}), '2')

    def test_conflicting_or_unsupported_versions_do_not_choose_latest(self):
        with self.assertRaises(InitError):
            self.detect('nextjs', {'node_modules/next/package.json': '{"version":"14.2.35"}', 'package-lock.json': '{"packages":{"node_modules/next":{"version":"16.0.0"}}}'})
        with self.assertRaises(InitError):
            self.detect('django', {'requirements.txt': 'Django==2.2.28\n'})

    def test_new_project_uses_explicit_registry_default(self):
        self.assertIsNone(self.detect('django', {}))


if __name__ == "__main__":
    unittest.main()
