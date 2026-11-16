"""Metadata-only fixtures for testing native command dispatch and lock protection."""
import json
import sys
from pathlib import Path

kind, package, version = sys.argv[1:]
root = Path('.')
if kind == 'composer':
    path = root / 'vendor/composer/installed.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'packages': [{'name': package, 'version': version + '.0'}]}))
elif kind == 'gem':
    (root / 'Gemfile.lock').write_text(f'GEM\n  specs:\n    {package} ({version}.0)\n')
    (root / '.ruby-version').write_text('3.4.6\n')
elif kind == 'go':
    (root / 'go.mod').write_text(f'module example.test\nrequire {package} v{version}.0.0\n')
    (root / 'go.sum').write_text('existing sums\n')
elif kind == 'cargo':
    (root / 'Cargo.lock').write_text(f'[[package]]\nname="{package}"\nversion="{version}.0"\n')
elif kind == 'swift':
    (root / 'Package.resolved').write_text(json.dumps({'pins': [{'identity': package, 'state': {'version': version + '.0.0'}}]}))
elif kind == 'mix':
    (root / 'mix.lock').write_text(f'%{{"{package}": {{:hex, :{package}, "{version}.0", "hash", [], [], "hexpm", "hash"}}}}\n')
elif kind == 'maven':
    (root / 'pom.xml').write_text(f'<project><parent><groupId>{package}</groupId><artifactId>framework-parent</artifactId><version>{version}.0.0</version></parent></project>')
elif kind == 'gradle':
    (root / 'gradle.lockfile').write_text(f'{package}:server-core:{version}.0.0=compileClasspath\n')
elif kind == 'nuget':
    (root / 'App.fsproj').write_text(f'<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup><ItemGroup><PackageReference Include="{package}" Version="{version}.0.0" /></ItemGroup></Project>')
elif kind == 'dotnet':
    (root / 'App.csproj').write_text(f'<Project><PropertyGroup><TargetFramework>net{version}.0</TargetFramework></PropertyGroup></Project>')
elif kind == 'flutter':
    (root / '.fvmrc').write_text('{"flutter":"3.38.0"}')
elif kind in ('shards', 'pub'):
    (root / ('shard.lock' if kind == 'shards' else 'pubspec.lock')).write_text(f'packages:\n  {package}:\n    source: hosted\n    version: "{version}.0"\n')
    if kind == 'pub':
        (root / '.dart_tool').mkdir(exist_ok=True)
        (root / '.dart_tool/package_config.json').write_text(json.dumps({'packages':[{'name':'test','rootUri':'../test-package/'}]}))
        (root / 'test-package/bin').mkdir(parents=True, exist_ok=True)
        (root / 'test-package/bin/test.dart').write_text('void main() {}')
elif kind == 'renv':
    (root / 'renv.lock').write_text(json.dumps({'Packages': {package: {'Version': version + '.0'}}}))
elif kind == 'julia':
    (root / 'Manifest.toml').write_text(f'manifest_format = "2.0"\n[[deps.{package}]]\nversion = "{version}.0"\n')
elif kind == 'cpan':
    (root / 'cpanfile.snapshot').write_text(f'DISTRIBUTIONS\n  {package}-{version}.0\n    provides:\n      {package} {version}.0\n')
elif kind == 'rebar':
    (root / 'rebar.lock').write_text(f'{{"1.2.0", [{{<<"{package}">>, {{pkg, <<"{package}">>, <<"{version}.0">>}}, 0}}]}}.\n')
elif kind == 'lein':
    (root / 'project.clj').write_text(f'(defproject fixture "0.0.1" :dependencies [[{package} "{version}.0"]])\n')
elif kind == 'cabal':
    (root / 'cabal.project.freeze').write_text(f'constraints: any.{package} =={version}.0\n')
elif kind == 'cpp':
    (root / 'conan.lock').write_text(json.dumps({'version':'0.5','requires':[f'{package}/{version}.0#recipehash']}))
else:
    raise ValueError(kind)
