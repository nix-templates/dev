"""Regression tests for graph detection and the expanded framework catalogue."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import test_versions
from dvt import InitError, detect_version, main
from test_dvt import CATALOGUE

ROOT = Path(__file__).parents[2]


class ExpandedMetadataTests(unittest.TestCase):
    fixture = test_versions.VersionTests.fixture
    def test_shards_and_pub_keep_package_boundaries(self):
        for kind, filename in [('shards', 'shard.lock'), ('pub', 'pubspec.lock')]:
            for newline in ('\n', ''):
                with self.subTest(kind=kind, newline=bool(newline)):
                    text = 'packages:\n  example:\n    version: "1.2.3"\n  unrelated:\n    version: "99.0.0"' + newline
                    self.assertEqual(self.fixture(kind, 'example', '1', {filename: text}), '1.2.3')
            with self.assertRaises(ValueError):
                self.fixture(kind, 'missing', '1', {filename: text})

    def test_renv_uses_lock_not_description_constraint(self):
        self.assertEqual(self.fixture('renv', 'shiny', '1', {'renv.lock': '{"Packages":{"shiny":{"Version":"1.9.1"}}}', 'DESCRIPTION': 'Imports: shiny (>= 1.0)'}), '1.9.1')

    def test_julia_manifest_formats_and_path_override(self):
        for prefix in ('', 'deps.'):
            self.assertEqual(self.fixture('julia', 'Genie', '5', {'Manifest.toml': f'[[{prefix}Genie]]\nversion="5.31.1"\n'}), '5.31.1')
        with self.assertRaises(ValueError):
            self.fixture('julia', 'Genie', '5', {'Manifest.toml': '[[deps.Genie]]\nversion="5.31.1"\npath="../fork"\n'})

    def test_cpan_snapshot_reads_module_version_not_distribution_filename(self):
        self.assertEqual(self.fixture('cpan', 'Mojolicious', '9', {'cpanfile.snapshot': 'DISTRIBUTIONS\n  Other-1.0\n    provides:\n      Mojolicious 9.40\n      Mojo 9.40\n'}), '9.40')

    def test_rebar_hex_version_and_git_rejection(self):
        self.assertEqual(self.fixture('rebar', 'cowboy', '2', {'rebar.lock': '{"1.2.0", [{<<"cowboy">>,{pkg,<<"cowboy">>,<<"2.12.0">>},0}]}.\n'}), '2.12.0')
        with self.assertRaises(ValueError):
            self.fixture('rebar', 'cowboy', '2', {'rebar.lock': '{<<"cowboy">>,{git,"../fork",{ref,"abc"}},0}.\n'})

    def test_lein_only_accepts_literal_dependency_version(self):
        self.assertEqual(self.fixture('lein', 'ring/ring-core', '1', {'project.clj': '; [ring/ring-core "9.0"]\n(defproject app "0" :dependencies [[ring/ring-core "1.14.2"]])'}), '1.14.2')
        with self.assertRaises(ValueError):
            self.fixture('lein', 'ring/ring-core', '1', {'project.clj': '(defproject app "0" :dependencies [[ring/ring-core version]])'})

    def test_cabal_freeze_excludes_similar_package_name(self):
        freeze = 'constraints: any.servant-server ==0.19.1,\n             any.servant ==0.20.2\n'
        self.assertEqual(self.fixture('cabal', 'servant', '0.20', {'cabal.project.freeze': freeze}), '0.20.2')

    def test_cpp_resolved_metadata_rejects_disagreement(self):
        lock = json.dumps({'requires': ['qt/6.8.2#hash']})
        self.assertEqual(self.fixture('cpp', 'qt', '6', {'conan.lock': lock}), '6.8.2')
        status = 'Package: qt\nVersion: 5.15.12\nStatus: install ok installed\n'
        with self.assertRaises(ValueError):
            self.fixture('cpp', 'qt', '6', {'conan.lock': lock, 'vcpkg_installed/vcpkg/status': status})

    def test_gradle_does_not_hide_ambiguous_lock_with_property(self):
        with self.assertRaises(ValueError):
            self.fixture('gradle', 'io.ktor', '3', {'gradle.lockfile': 'io.ktor:core:3.0.1=compile\nio.ktor:tests:2.3.0=test\n', 'gradle.properties': 'ktor_version=3.0.1'})
        self.assertEqual(self.fixture('gradle', 'org.apache.grails', '7', {'gradle.properties': 'grailsVersion=7.0.1\n'}), '7.0.1')


class NodeWorkspaceTests(unittest.TestCase):
    def read(self, files, package='react', at='apps/web'):
        import version_guard
        with tempfile.TemporaryDirectory() as tmp:
            for name, value in files.items():
                path = Path(tmp)/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)
            root = Path(tmp)/at
            root.mkdir(parents=True, exist_ok=True)
            return version_guard.node_locked(package, root)

    def test_npm_workspace_uses_its_own_resolved_package(self):
        files = {'package.json': '{"workspaces":["apps/*"]}', 'package-lock.json': '{"packages":{"apps/web/node_modules/react":{"version":"18.3.1"},"node_modules/react":{"version":"19.0.0"}}}'}
        self.assertEqual(self.read(files), {'18.3.1'})
        files['package.json'] = '{}'
        self.assertEqual(self.read(files), set())

    def test_pnpm_importers_and_peer_suffix(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest('PyYAML is provided by the packaged CLI')
        files = {'pnpm-workspace.yaml': 'packages:\n  - apps/*\n', 'pnpm-lock.yaml': "lockfileVersion: '9.0'\nimporters:\n  apps/web:\n    dependencies:\n      react:\n        specifier: ^19\n        version: 19.0.0(react-dom@19.0.0)\n"}
        self.assertEqual(self.read(files), {'19.0.0'})

    def test_yarn_selectors_do_not_mix_workspace_release_lines(self):
        base = {'package.json': '{"workspaces":["apps/*"]}', 'apps/web/package.json': '{"dependencies":{"react":"^18"}}'}
        classic = '\n"react@^18":\n  version "18.3.1"\n\n"react@^19":\n  version "19.0.0"\n'
        self.assertEqual(self.read(base | {'yarn.lock': classic}), {'18.3.1'})
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest('PyYAML is provided by the packaged CLI')
        modern = '__metadata:\n  version: 8\n"react@npm:^18":\n  version: 18.3.1\n"react@npm:^19":\n  version: 19.0.0\n'
        self.assertEqual(self.read(base | {'yarn.lock': modern}), {'18.3.1'})

    def test_workspace_manager_comes_from_the_declared_root(self):
        import version_guard
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); child=root/'apps/web'; child.mkdir(parents=True)
            (root/'package.json').write_text('{"workspaces":["apps/*"],"packageManager":"yarn@4.6.0"}')
            self.assertEqual(version_guard.node_manager(child), 'yarn')
            (root/'package.json').write_text('{"packageManager":"yarn@4.6.0"}')
            self.assertEqual(version_guard.node_manager(child), 'npm')

    def test_hoisted_binary_only_uses_declared_workspace(self):
        import version_guard
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); child=root/'apps/web'; child.mkdir(parents=True)
            (root/'node_modules/.bin').mkdir(parents=True)
            executable=root/'node_modules/.bin/tsc'; executable.touch()
            (root/'package.json').write_text('{"workspaces":["apps/*"]}')
            self.assertEqual(version_guard.node_binary('tsc', child), executable)
            (root/'package.json').write_text('{}')
            with self.assertRaises(ValueError):
                version_guard.node_binary('tsc', child)


class ExpandedGeneratorTests(unittest.TestCase):
    def detect(self, name, files):
        catalogue = dict(CATALOGUE, versionReader=str(ROOT / 'frameworks/version_guard.py'))
        with tempfile.TemporaryDirectory() as tmp:
            for name_, data in files.items():
                path = Path(tmp) / name_
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(data)
            return detect_version(name, tmp, catalogue)

    def test_fiber_and_grails_release_lines_use_different_coordinates(self):
        for version in ('2', '3'):
            self.assertEqual(self.detect('fiber', {'go.mod': f'module app\nrequire github.com/gofiber/fiber/v{version} v{version}.0.0\n'}), version)
        self.assertEqual(self.detect('grails', {'gradle.lockfile': 'org.apache.grails:grails-core:7.0.0=compileClasspath\n'}), '7')

    def test_ambiguous_native_metadata_never_defaults_to_newest(self):
        with self.assertRaises(InitError):
            self.detect('axum', {'Cargo.lock': '[[package]]\nname="axum"\nversion="0.7.9"\n[[package]]\nname="axum"\nversion="0.8.1"\n'})
        with self.assertRaises(InitError):
            self.detect('kemal', {'shard.lock': 'not valid lock metadata'})
        self.assertIsNone(self.detect('kemal', {}))

    def test_composer_detection_before_install(self):
        self.assertEqual(self.detect('cakephp', {'composer.lock': '{"packages":[{"name":"cakephp/cakephp","version":"4.6.0"}]}'}), '4')

    def test_list_counts_are_computed_from_registry(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['list', '--json'], CATALOGUE), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data['counts']['frameworks'], len(data['frameworks']))
        self.assertEqual(data['counts']['release_lines'], sum(len(p['versions']) for p in data['frameworks'].values()))

    def test_describe_exposes_release_constraints_and_evidence(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['describe', 'angular'], CATALOGUE), 0)
        profile = json.loads(out.getvalue())
        self.assertEqual(profile['requires'][0]['package'], '@angular/cli')
        self.assertEqual(profile['validation'], 'tool-and-adapter')


class DartEntrypointTests(unittest.TestCase):
    def test_existing_package_entrypoint_and_missing_dependency(self):
        spec = importlib.util.spec_from_file_location('dart_test_path', ROOT / 'frameworks/dart-test-path.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.dart_tool').mkdir()
            (root / 'cached test/bin').mkdir(parents=True)
            (root / 'cached test/bin/test.dart').write_text('void main() {}')
            (root / '.dart_tool/package_config.json').write_text(json.dumps({'packages': [{'name': 'test', 'rootUri': '../cached%20test/'}]}))
            self.assertEqual(module.test_entry(root), root / 'cached test/bin/test.dart')
            (root / 'cached test/bin/test.dart').unlink()
            with self.assertRaises(ValueError):
                module.test_entry(root)


if __name__ == '__main__':
    unittest.main()
