import json
import tempfile
import unittest
from pathlib import Path

from version_guard import check, installed


class VersionTests(unittest.TestCase):
    def fixture(self, kind, package, expected, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            return check(kind, package, expected, root)

    def test_installed_node_version_not_manifest_range_or_tool_bundle(self):
        self.assertEqual(self.fixture('npm', 'next', '14', {
            'package.json': '{"dependencies":{"next":"^16"}}',
            'node_modules/next/package.json': '{"version":"14.2.35"}',
        }), '14.2.35')
        with self.assertRaises(ValueError):
            self.fixture('npm', 'next', '16', {'node_modules/next/package.json': '{"version":"14.2.35"}'})

    def test_composer_installed_formats(self):
        package = {'name': 'laravel/framework', 'version': 'v12.3.4'}
        for metadata in ([package], {'packages': [package]}):
            self.assertEqual(self.fixture('composer', 'laravel/framework', '12', {'vendor/composer/installed.json': json.dumps(metadata)}), '12.3.4')

    def test_cargo_rejects_ambiguous_framework_versions(self):
        lock = '[[package]]\nname="axum"\nversion="0.8.1"\n'
        self.assertEqual(self.fixture('cargo', 'axum', '0.8', {'Cargo.lock': lock}), '0.8.1')
        with self.assertRaises(ValueError):
            self.fixture('cargo', 'axum', '0.8', {'Cargo.lock': lock + '[[package]]\nname="axum"\nversion="0.7.0"\n'})

    def test_go_selects_required_version_and_rejects_replacements(self):
        mod = 'module example.test\nrequire (\n github.com/gin-gonic/gin v1.10.0\n)\n'
        self.assertEqual(self.fixture('go', 'github.com/gin-gonic/gin', '1', {'go.mod': mod}), '1.10.0')
        for replace in ('replace github.com/gin-gonic/gin => ../fork', 'replace (\ngithub.com/gin-gonic/gin => ../fork\n)'):
            with self.assertRaises(ValueError):
                self.fixture('go', 'github.com/gin-gonic/gin', '1', {'go.mod': mod + replace})

    def test_gem_lock_does_not_accept_an_unrelated_gem(self):
        self.assertEqual(self.fixture('gem', 'rails', '8.1', {'Gemfile.lock': 'GEM\n  specs:\n    rails (8.1.2)\n'}), '8.1.2')
        with self.assertRaises(ValueError):
            self.fixture('gem', 'rails', '8.1', {'Gemfile.lock': '    not-rails (8.1.2)\n'})

    def test_mix_lock(self):
        self.assertEqual(self.fixture('mix', 'phoenix', '1.8', {'mix.lock': '%{\n "phoenix": {:hex, :phoenix, "1.8.1", "hash", [:mix], [], "hexpm", "hash"},\n}\n'}), '1.8.1')

    def test_maven_resolves_explicit_version_property(self):
        pom = '<project xmlns="http://maven.apache.org/POM/4.0.0"><properties><boot.version>3.5.1</boot.version></properties><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>${boot.version}</version></parent></project>'
        self.assertEqual(self.fixture('maven', 'org.springframework.boot', '3', {'pom.xml': pom}), '3.5.1')

    def test_gradle_lock_and_catalogue(self):
        for files in ({'gradle.lockfile': 'io.ktor:ktor-server-core:3.0.1=compileClasspath\n'}, {'gradle/libs.versions.toml': '[versions]\nktor="3.0.1"\n'}, {'gradle.properties': 'ktor_version=3.0.1\n'}):
            self.assertEqual(self.fixture('gradle', 'io.ktor', '3', files), '3.0.1')

    def test_swift_resolved_formats(self):
        for metadata in ({'pins': [{'identity': 'vapor', 'state': {'version': '4.110.1'}}]}, {'object': {'pins': [{'package': 'Vapor', 'state': {'version': '4.110.1'}}]}}):
            self.assertEqual(self.fixture('swift', 'vapor', '4', {'Package.resolved': json.dumps(metadata)}), '4.110.1')

    def test_dotnet_target_framework(self):
        self.assertEqual(self.fixture('dotnet', 'Microsoft.AspNetCore.App', '8', {'App.csproj': '<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>'}), '8')

    def test_giraffe_version_is_independent_of_dotnet_sdk(self):
        self.assertEqual(self.fixture('nuget', 'Giraffe', '7', {'App.fsproj': '<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup><ItemGroup><PackageReference Include="Giraffe" Version="7.0.2" /></ItemGroup></Project>'}), '7.0.2')
        with self.assertRaises(ValueError):
            self.fixture('nuget', 'Giraffe', '8', {'packages.lock.json': '{"dependencies":{"net8.0":{"Giraffe":{"resolved":"7.0.2"}}}}'})

    def test_missing_metadata_fails(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(OSError):
            installed('npm', 'next', Path(tmp))


if __name__ == '__main__':
    unittest.main()
