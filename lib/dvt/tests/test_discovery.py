"""Discovery covers ecosystem fixtures, monorepos and existing tool ownership."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from discovery import configured_tools, discover
from dvt import detect_version, generate_discovered, main
from test_dvt import CATALOGUE

LIB = Path(__file__).parents[2]
REPO = LIB.parent
PATHS = [str(LIB / 'ci'), str(LIB / 'layers'), str(REPO / 'mcp')]
MARKS = {name: {'marks': None, 'insteadOf': []} for name in ('python', 'node', 'php', 'ruby', 'go', 'rust', 'java', 'kotlin', 'r', 'julia', 'c-cpp', 'dart', 'crystal', 'elixir', 'erlang', 'clojure', 'haskell', 'perl')}
MARKS['typescript'] = {'marks': ['tsconfig.json'], 'insteadOf': ['node']}


def catalogue():
    if os.environ.get('DVT_TEST_CATALOGUE'):
        return json.loads(Path(os.environ['DVT_TEST_CATALOGUE']).read_text())
    return dict(CATALOGUE, readerPaths=PATHS, marks=MARKS, versionReader=str(LIB / 'frameworks/version_guard.py'))


class DiscoveryTests(unittest.TestCase):
    def inspect(self, files, exclude=()):
        with tempfile.TemporaryDirectory() as tmp:
            for filename, content in files.items():
                path = Path(tmp) / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            before = {str(p.relative_to(tmp)): p.read_bytes() for p in Path(tmp).rglob('*') if p.is_file()}
            plan = discover(tmp, catalogue(), detect_version, exclude)
            after = {str(p.relative_to(tmp)): p.read_bytes() for p in Path(tmp).rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            return plan

    def test_multiple_languages_keep_their_roots_and_original_tool_configs(self):
        plan = self.inspect({
            'api/requirements.txt': 'Flask==3.1.2\n', 'api/app.py': 'pass\n',
            'api/pyproject.toml': '[tool.ruff]\n[tool.bandit]\n[tool.importlinter]\nroot_package="app"\n',
            'web/package.json': '{"dependencies":{"vue":"3.5.0"},"scripts":{"test":"vitest run"}}',
            'web/node_modules/vue/package.json': '{"version":"3.5.0"}',
            'web/.dependency-cruiser.cjs': 'module.exports = { forbidden: [] };',
            'worker/go.mod': 'module app\nrequire github.com/go-chi/chi/v5 v5.2.0\n',
            'worker/main.go': 'package main\n', 'worker/.golangci.yml': 'version: "2"\n',
        })
        self.assertEqual(set(plan['components']), {'api', 'web', 'worker'})
        self.assertEqual(plan['components']['api']['frameworks'], [{'name':'flask','version':'3.1'}])
        self.assertEqual(plan['components']['web']['configured']['architecture'][0]['argv'], ['depcruise','--config','.dependency-cruiser.cjs','.'])
        self.assertEqual(plan['components']['api']['configured']['architecture'][0]['runner'], 'python')
        self.assertEqual(plan['components']['worker']['frameworks'], [{'name':'chi','version':'5'}])
        self.assertNotIn('architecture', plan['components']['worker']['enabledCommands'])

    def test_scripts_are_authoritative_and_never_executed_during_discovery(self):
        plan = self.inspect({'package.json': json.dumps({'scripts': {'architecture':'touch DO_NOT_CREATE', 'security':'custom-sast', 'quality':'custom-quality', 'style':'custom-style', 'test':'custom-tests'}}), '.dependency-cruiser.cjs':'throw new Error("do not execute")', 'eslint.config.js':'throw new Error("do not execute")', '.semgrep.yml':'rules: []'})
        cfg = plan['components']['root']['configured']
        self.assertEqual(set(cfg), {'quality','style','security','architecture','tests'})
        self.assertEqual(cfg['architecture'], [{'runner':'script','argv':['architecture']}])
        self.assertEqual(cfg['security'], [{'runner':'script','argv':['security']}])

    def test_host_framework_wins_but_underlying_libraries_are_reported(self):
        plan = self.inspect({'package.json':'{"dependencies":{"next":"15.1.0","react":"19.0.0"}}', 'node_modules/next/package.json':'{"version":"15.1.0"}', 'node_modules/react/package.json':'{"version":"19.0.0"}'})
        self.assertEqual(plan['components']['root']['frameworks'], [{'name':'nextjs','version':'15'}])
        self.assertEqual(set(plan['detected'][0]['detectedFrameworks']), {'nextjs','react'})

    def test_vendor_virtualenv_build_and_explicit_exclusions_are_not_projects(self):
        plan = self.inspect({'src/main.py':'pass', '.venv/dependency/package.json':'{"dependencies":{"next":"^999"}}', 'node_modules/dependency/package.json':'{}', 'build/dep/requirements.txt':'Django==1.0', 'samples/package.json':'{"dependencies":{"next":"^999"}}'}, exclude=['samples'])
        self.assertEqual(set(plan['components']), {'root'})
        self.assertEqual(plan['components']['root']['frameworks'], [])

    def test_unknown_version_does_not_silently_generate_latest_profile(self):
        with self.assertRaises(ValueError):
            self.inspect({'package.json':'{"dependencies":{"express":"^5"}}'})

    def test_framework_version_conflict_is_reported(self):
        with self.assertRaises(Exception) as error:
            self.inspect({'package.json':'{"dependencies":{"express":"^5"}}', 'node_modules/express/package.json':'{"version":"4.20.0"}', 'package-lock.json':'{"packages":{"node_modules/express":{"version":"5.0.0"}}}'})
        self.assertIn('conflicting', str(error.exception))

    def test_existing_architecture_file_is_optional_and_preserved(self):
        plan = self.inspect({'main.py':'pass', 'architecture.toml':'[[layer]]\nname="app"\npaths=["."]\n'})
        self.assertTrue(plan['detected'][0]['builtinArchitecture'])
        self.assertIn('architecture', plan['components']['root']['enabledCommands'])

    def test_php_ruby_jvm_and_sql_use_the_owning_tool(self):
        for files, category, runner, tool in [
            ({'deptrac.yaml':'deptrac: {}'},'architecture','php','vendor/bin/deptrac'),
            ({'packwerk.yml':'package_paths: []'},'architecture','ruby','packwerk'),
            ({'gradlew':'#!/bin/sh', 'build.gradle':'plugins { id "com.autonomousapps.dependency-analysis" }'},'architecture','gradle','buildHealth'),
            ({'mvnw':'#!/bin/sh', 'pom.xml':'<project><artifactId>maven-enforcer-plugin</artifactId></project>'},'architecture','maven','enforcer:enforce'),
            ({'.sqlfluff':'[sqlfluff]\ntemplater = dbt\n'},'quality','python','sqlfluff'),
        ]:
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as tmp:
                for name, content in files.items(): (Path(tmp)/name).write_text(content)
                config, _ = configured_tools(Path(tmp))
                self.assertEqual(config[category][0]['runner'], runner)
                self.assertEqual(config[category][0]['argv'][0], tool)

    def test_auto_init_dry_run_and_inspect_write_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'main.py').write_text('pass')
            for args in (['init','--dry-run'], ['inspect']):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(main([*args,'-d',tmp], catalogue()),0)
                self.assertTrue(json.loads(out.getvalue()))
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ['main.py'])

    def test_nested_virtualenvs_are_ignored(self):
        plan = self.inspect({'app/main.py': 'pass', 'app/.venv/fake/package.json': '{"dependencies":{"next":"^999"}}'})
        self.assertEqual(set(plan['components']), {'root'})

    def test_independent_framework_overlap_requires_review(self):
        plan = self.inspect({'requirements.txt': 'Flask==3.1.2\nDjango==5.2.1\n'})
        self.assertTrue(any('overlaps' in warning for warning in plan['warnings']))

    def test_every_registered_release_line_is_discoverable(self):
        for name, profile in catalogue()['frameworks'].items():
            for version in profile['versions']:
                with self.subTest(framework=name, version=version), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    meta = profile | profile.get('variants', {}).get(version, {})
                    if 'distribution' in meta:
                        (root/'requirements.txt').write_text(f"{meta['distribution']}=={version}.0\n")
                    elif meta.get('adapter') == 'node':
                        (root/'package.json').write_text(json.dumps({'dependencies': {meta['package']: version+'.0'}}))
                        path = root/'node_modules'/meta['package']/'package.json'
                        path.parent.mkdir(parents=True)
                        path.write_text(json.dumps({'version': version+'.0'}))
                    else:
                        subprocess.run([sys.executable, str(LIB/'frameworks/tests/native-fixture.py'), meta['kind'], meta['package'], version], cwd=root, check=True, capture_output=True)
                        if meta['kind'] == 'dotnet':
                            (root/'App.csproj').write_text(f'<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net{version}.0</TargetFramework></PropertyGroup></Project>')
                        if meta['kind'] == 'flutter':
                            (root/'pubspec.yaml').write_text('dependencies:\n  flutter:\n    sdk: flutter\n')
                    plan = discover(tmp, catalogue(), detect_version)
                    selected = [f for component in plan['components'].values() for f in component['frameworks']]
                    self.assertIn({'name':name, 'version':version}, selected)

    def test_every_language_uses_the_existing_language_detector(self):
        if not os.environ.get('DVT_TEST_CATALOGUE'):
            self.skipTest('Nix provides the complete language metadata')
        sys.path.insert(0,str(LIB/'ci/tests'))
        from samples import SAMPLES
        for language, (files, expected) in SAMPLES.items():
            with self.subTest(language=language):
                # The test samples are source-only and do not install frameworks.
                plan=self.inspect(files)
                actual={name for entry in plan['detected'] for name in entry['languages']}
                self.assertEqual(actual, expected)
                generated=generate_discovered(plan,catalogue())
                with tempfile.NamedTemporaryFile(suffix='.nix', mode='w') as handle:
                    handle.write(generated['flake.nix']); handle.flush()
                    result=subprocess.run(['nix-instantiate','--parse',handle.name],capture_output=True,text=True,check=False)
                    self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
