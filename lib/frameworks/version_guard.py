"""Read installed framework metadata without importing framework code."""

import fnmatch
import json
import re
import sys
import tomllib
from pathlib import Path


def one_version(versions, package):
    values = set(versions)
    if len(values) != 1:
        raise ValueError(f'{package} needs one explicit resolved version; found {sorted(values)}')
    value = values.pop()
    if not re.fullmatch(r'\d+(?:\.\d+)*(?:[-+~][A-Za-z0-9.-]+)?', value):
        raise ValueError(f'{package} has an unsupported non-release version {value!r}')
    return value


def yaml_package_version(path, package):
    """Read the fixed package blocks emitted by Shards and Pub (no YAML eval)."""
    content = path.read_text()
    blocks = re.findall(r'(?m)^  ' + re.escape(package) + r':\s*\n((?:[ \t]+[^\n]*\n|\n)*)', content)
    # Limit each block to its package, not subsequent siblings at two spaces.
    values = []
    for block in blocks:
        block = re.split(r'(?m)^  \S', block, maxsplit=1)[0]
        values.extend(re.findall(r'''(?m)^    version:\s*["']?([0-9][^\s"']*)["']?\s*$''', block))
    return one_version(values, package)


METADATA = {
    'npm': ['package-lock.json', 'node_modules/*/package.json', 'node_modules/@*/*/package.json'],
    'composer': ['composer.lock', 'vendor/composer/installed.json'],
    'gem': ['Gemfile.lock'], 'go': ['go.mod'], 'cargo': ['Cargo.lock'],
    'swift': ['Package.resolved'], 'mix': ['mix.lock'],
    'maven': ['pom.xml', 'gradle.lockfile', 'gradle/dependency-locks/*.lockfile', 'gradle.properties', 'gradle/libs.versions.toml'],
    'gradle': ['gradle.lockfile', 'gradle/dependency-locks/*.lockfile', 'gradle.properties', 'gradle/libs.versions.toml'],
    'nuget': ['obj/project.assets.json', 'packages.lock.json', '*.csproj', '*.fsproj', 'Directory.Packages.props'],
    'dotnet': ['*.csproj', '*.fsproj', 'Directory.Build.props'],
    'shards': ['shard.lock'], 'pub': ['pubspec.lock'], 'gleam': ['manifest.toml'],
    'renv': ['renv.lock'], 'julia': ['Manifest.toml'], 'cpan': ['cpanfile.snapshot'],
    'rebar': ['rebar.lock'], 'lein': ['project.clj'], 'cabal': ['cabal.project.freeze'],
    'cpp': ['conan.lock', 'vcpkg_installed/vcpkg/status', 'build/vcpkg_installed/vcpkg/status'],
}


def has_metadata(kind, root=Path('.')):
    return any(next(root.glob(pattern), None) is not None for pattern in METADATA.get(kind, []))


def node_roots(root):
    root = root.resolve()
    yield root
    for parent in root.parents:
        package_json = parent / 'package.json'
        patterns = []
        if package_json.is_file():
            workspaces = json.loads(package_json.read_text()).get('workspaces', [])
            patterns = workspaces.get('packages', []) if isinstance(workspaces, dict) else workspaces
        pnpm = parent / 'pnpm-workspace.yaml'
        if pnpm.is_file():
            patterns += read_yaml(pnpm).get('packages', [])
        relative = root.relative_to(parent).as_posix()
        if any(fnmatch.fnmatchcase(relative, pattern.rstrip('/')) for pattern in patterns if not pattern.startswith('!')) and not any(fnmatch.fnmatchcase(relative, pattern[1:].rstrip('/')) for pattern in patterns if pattern.startswith('!')):
            yield parent


def read_yaml(path):
    # Safe YAML supports lockfile syntax/anchors but never executes constructors.
    import yaml
    class UniqueLoader(yaml.SafeLoader):
        pass
    def mapping(loader, node, deep=False):
        loader.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError(f'{path}: duplicate YAML key {key!r}')
            result[key] = loader.construct_object(value_node, deep=deep)
        return result
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        return yaml.load(path.read_text(), Loader=UniqueLoader) or {}
    except yaml.YAMLError as error:
        raise ValueError(f'{path}: invalid YAML: {error}') from error


def node_locked(package, root):
    values = set()
    manifest = root / 'package.json'
    declared = json.loads(manifest.read_text()) if manifest.is_file() else {}
    selectors = {package + '@' + prefix + value for section in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies') for key, value in declared.get(section, {}).items() if key == package for prefix in ('', 'npm:')}
    def selected(selector):
        return selector in selectors if selectors else selector.startswith(package + '@')
    for at in node_roots(root):
        lock = at / 'package-lock.json'
        if lock.exists():
            data = json.loads(lock.read_text())
            relative = root.resolve().relative_to(at).as_posix()
            prefix = '' if relative == '.' else relative + '/'
            entry = data.get('packages', {}).get(prefix + 'node_modules/' + package)
            entry = entry or data.get('packages', {}).get('node_modules/' + package) or data.get('dependencies', {}).get(package, {})
            if entry.get('version'):
                values.add(entry['version'])
        lock = at / 'pnpm-lock.yaml'
        if lock.exists():
            data = read_yaml(lock)
            relative = root.resolve().relative_to(at).as_posix()
            importer = data.get('importers', {}).get(relative, data if relative == '.' else {})
            for section in ('dependencies', 'devDependencies', 'optionalDependencies'):
                entry = importer.get(section, {}).get(package)
                if entry:
                    version = entry.get('version') if isinstance(entry, dict) else entry
                    version = str(version).split('(', 1)[0]
                    if re.fullmatch(r'\d[^\s]*', version):
                        values.add(version)
        lock = at / 'yarn.lock'
        if lock.exists():
            text = lock.read_text()
            if '__metadata:' in text:
                data = read_yaml(lock)
                for lock_selectors, entry in data.items():
                    if lock_selectors == '__metadata' or not isinstance(entry, dict):
                        continue
                    if any(selected(selector.strip()) for selector in lock_selectors.split(', ')) and entry.get('version'):
                        values.add(str(entry['version']))
            else:
                # Yarn classic's block keys aren't standard YAML mappings.
                for block in re.split(r'\n(?=\S)', text):
                    header, _, body = block.partition('\n')
                    lock_selectors = header.rstrip(':').replace('"', '').split(', ')
                    if any(selected(selector) for selector in lock_selectors):
                        match = re.search(r'^  version "([^"\n]+)"', body, re.MULTILINE)
                        if match:
                            values.add(match[1])
    return values


def node_manager(root=Path('.')):
    for at in node_roots(root):
        manifest = at / 'package.json'
        if manifest.is_file():
            declared = json.loads(manifest.read_text()).get('packageManager', '').split('@', 1)[0]
            if declared in ('npm', 'pnpm', 'yarn', 'bun'):
                return declared
        for lock, manager in [('pnpm-lock.yaml', 'pnpm'), ('yarn.lock', 'yarn'), ('bun.lock', 'bun'), ('bun.lockb', 'bun'), ('package-lock.json', 'npm')]:
            if (at / lock).is_file():
                return manager
    return 'npm'


def yarn_path(root=Path('.')):
    for at in node_roots(root):
        config = at / '.yarnrc.yml'
        if config.is_file():
            path = read_yaml(config).get('yarnPath')
            if path:
                binary = (at / path).resolve()
                if not binary.is_file():
                    raise ValueError('Configured yarnPath is missing; no package manager was installed')
                return binary
    raise ValueError('No project yarnPath; set DVT_PROJECT_YARN to an existing Yarn executable')


def node_binary(name, root=Path('.')):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
        raise ValueError('invalid project executable name')
    for at in node_roots(root):
        path = at / 'node_modules/.bin' / name
        if path.is_file():
            return path
    raise ValueError(f'Project tool {name} is missing; no dependency was added')


def installed(kind, package, root=Path('.')):

    if kind in ('shards', 'pub'):
        return yaml_package_version(root / ('shard.lock' if kind == 'shards' else 'pubspec.lock'), package)
    if kind == 'gleam':
        data = tomllib.loads((root / 'manifest.toml').read_text())
        return one_version((p['version'] for p in data['packages'] if p['name'] == package and p.get('source') == 'hex'), package)
    if kind == 'renv':
        return one_version([json.loads((root / 'renv.lock').read_text())['Packages'][package]['Version']], package)
    if kind == 'julia':
        data = tomllib.loads((root / 'Manifest.toml').read_text())
        entries = data.get('deps', data).get(package, [])
        return one_version((p['version'] for p in entries if 'path' not in p), package)
    if kind == 'cpan':
        content = (root / 'cpanfile.snapshot').read_text()
        return one_version(re.findall(r'(?m)^      ' + re.escape(package) + r'\s+(\d[^\s]*)\s*$', content), package)
    if kind == 'rebar':
        content = (root / 'rebar.lock').read_text()
        return one_version(re.findall(r'\{<<"' + re.escape(package) + r'">>,\s*\{pkg,\s*<<"' + re.escape(package) + r'">>,\s*<<"([^"\n]+)">>', content), package)
    if kind == 'lein':
        content = (root / 'project.clj').read_text()
        content = re.sub(r'(?m);[^\n]*', '', content)
        return one_version(re.findall(r'\[\s*' + re.escape(package) + r'\s+"(\d[^"\n]*)"', content), package)
    if kind == 'cabal':
        content = (root / 'cabal.project.freeze').read_text()
        return one_version(re.findall(r'(?:^|[\s,])(?:any\.)?' + re.escape(package) + r'\s*==\s*([0-9.]+)(?=[\s,]|$)', content), package)
    if kind == 'cpp':
        values = []
        lock = root / 'conan.lock'
        if lock.exists():
            # Conan calls GoogleTest gtest; vcpkg calls it gtest too.
            for reference in json.loads(lock.read_text()).get('requires', []):
                match = re.fullmatch(re.escape(package) + r'/([^#@]+)(?:[#@].*)?', reference)
                if match:
                    values.append(match[1])
        for path in (root / 'vcpkg_installed/vcpkg/status', root / 'build/vcpkg_installed/vcpkg/status'):
            if path.exists():
                for paragraph in path.read_text().split('\n\n'):
                    fields = dict(re.findall(r'(?m)^([A-Za-z-]+): (.+)$', paragraph))
                    if fields.get('Package') in ({'qt', 'qtbase'} if package == 'qt' else {package}) and fields.get('Status', '').endswith(' installed'):
                        values.append(fields['Version'])
        return one_version(values, package)

    if kind == 'npm':
        # Follow declared workspaces only, never a tool bundle or arbitrary
        # ancestor node_modules directory. PnP uses its unambiguous lock entry.
        for at in node_roots(root):
            path = at / 'node_modules' / package / 'package.json'
            if path.is_file():
                return json.loads(path.read_text())['version']
        if any((at / '.pnp.cjs').is_file() for at in node_roots(root)):
            return one_version(node_locked(package, root), package)
        raise FileNotFoundError(f'{package} is not installed for this project')
    if kind == 'composer':
        metadata = json.loads((root / 'vendor/composer/installed.json').read_text())
        packages = metadata if isinstance(metadata, list) else metadata['packages']
        return one_version((item['version'].lstrip('v') for item in packages if item['name'] == package), package)
    if kind == 'nuget':
        versions = set()
        assets = root / 'obj/project.assets.json'
        if assets.exists():
            for library in json.loads(assets.read_text()).get('libraries', {}):
                identity, _, version = library.partition('/')
                if identity.lower() == package.lower():
                    versions.add(version)
        lock = root / 'packages.lock.json'
        if lock.exists():
            for framework in json.loads(lock.read_text()).get('dependencies', {}).values():
                for identity, value in framework.items():
                    if identity.lower() == package.lower() and value.get('resolved'):
                        versions.add(value['resolved'])
        if not versions:
            import xml.etree.ElementTree as ET
            for path in [*root.glob('*.fsproj'), *root.glob('*.csproj'), root / 'Directory.Packages.props']:
                if not path.exists():
                    continue
                for node in ET.fromstring(path.read_text()).iter():
                    if node.attrib.get('Include', '').lower() == package.lower():
                        value = node.attrib.get('Version')
                        if not value:
                            value = next((child.text for child in node if child.tag.rsplit('}', 1)[-1] == 'Version'), None)
                        if value and re.fullmatch(r'\d+(?:\.\d+)+(?:[-.][A-Za-z0-9]+)*', value):
                            versions.add(value)
        if len(versions) == 1:
            return versions.pop()
        raise ValueError(f'{package} needs one explicit NuGet package version, independently of the .NET SDK version')
    if kind == 'dotnet':
        import xml.etree.ElementTree as ET
        versions = set()
        for path in [*root.glob('*.csproj'), *root.glob('*.fsproj'), root / 'Directory.Build.props']:
            if not path.exists():
                continue
            for node in ET.fromstring(path.read_text()).iter():
                if node.tag.rsplit('}', 1)[-1] in ('TargetFramework', 'TargetFrameworks'):
                    for framework in (node.text or '').split(';'):
                        match = re.fullmatch(r'net(\d+)\.\d+', framework.strip())
                        if match:
                            versions.add(match[1])
        if len(versions) == 1:
            return versions.pop()
        raise ValueError('select a project directory with one explicit .NET target release line')
    if kind == 'flutter':
        import os
        import subprocess
        command = os.environ.get('DVT_PROJECT_FLUTTER', package)
        result = subprocess.run([command, '--version', '--machine'], check=True, capture_output=True, text=True)
        metadata = json.loads(result.stdout)
        actual = metadata['frameworkVersion']
        fvm = root / '.fvmrc'
        if fvm.exists():
            required = json.loads(fvm.read_text())['flutter']
            if re.fullmatch(r'\d+\.\d+\.\d+', required) and actual != required:
                raise ValueError(f'Flutter {actual} does not match .fvmrc {required}; select the matching tooling package set')
        return actual
    if kind == 'swift':
        metadata = json.loads((root / 'Package.resolved').read_text())
        pins = metadata.get('pins', metadata.get('object', {}).get('pins', []))
        return next(item['state']['version'] for item in pins if item.get('identity', item.get('package', '')).lower() == package.lower())
    if kind == 'mix':
        content = (root / 'mix.lock').read_text()
        found = re.search(r'["\']?' + re.escape(package) + r'["\']?\s*(?::|=>)\s*\{\s*:hex,\s*:' + re.escape(package) + r',\s*"([^"]+)"', content)
        if not found:
            raise ValueError(f'{package} is not locked as a Hex dependency')
        return found[1]
    if kind == 'maven':
        if not (root / 'pom.xml').exists():
            return installed('gradle', package, root)
        import xml.etree.ElementTree as ET
        tree = ET.fromstring((root / 'pom.xml').read_text())
        def local(tag):
            return tag.rsplit('}', 1)[-1]
        props = {}
        for node in tree.iter():
            if local(node.tag) == 'properties':
                props.update({local(item.tag): (item.text or '').strip() for item in node})
        found = set()
        for node in tree.iter():
            fields = {local(item.tag): (item.text or '').strip() for item in node}
            if fields.get('groupId') == package and fields.get('version'):
                value = fields['version']
                for _ in range(10):
                    changed = re.sub(r'\$\{([^}]+)\}', lambda m: props.get(m[1], m[0]), value)
                    if value == changed:
                        break
                    value = changed
                if re.fullmatch(r'\d+(?:\.\d+)+(?:[-.][A-Za-z0-9]+)*', value):
                    found.add(value)
        if len(found) == 1:
            return found.pop()
        raise ValueError(f'{package} has no unambiguous explicit version in pom.xml')
    if kind == 'gradle':
        locks = [root / 'gradle.lockfile', *root.glob('gradle/dependency-locks/*.lockfile')]
        versions = set()
        for lock in locks:
            if lock.exists():
                versions.update(re.findall(r'(?m)^' + re.escape(package) + r':[^:]+:([^=\s]+)=', lock.read_text()))
        if len(versions) == 1:
            return versions.pop()
        if len(versions) > 1:
            raise ValueError(f'{package} has conflicting Gradle lock versions')
        # Common explicit version properties/catalogues are safe to read; do
        # not execute a build script to discover or resolve dependencies.
        key = {'io.ktor': 'ktor', 'org.springframework.boot': 'spring-boot', 'io.quarkus.platform': 'quarkus', 'io.micronaut.platform': 'micronaut', 'org.grails': 'grails', 'org.apache.grails': 'grails', 'org.spockframework': 'spock', 'io.dropwizard': 'dropwizard'}.get(package, package)
        properties = root / 'gradle.properties'
        if properties.exists():
            match = re.search(r'(?im)^' + key.replace('-', '[-_]') + r'(?:[._-]?version)?\s*=\s*(\d[^\s]*)', properties.read_text())
            if match:
                return match[1]
        catalogue = root / 'gradle/libs.versions.toml'
        if catalogue.exists():
            value = tomllib.loads(catalogue.read_text()).get('versions', {}).get(key)
            if isinstance(value, str):
                return value
        raise ValueError(f'{package} needs an explicit version in the existing Gradle lock, properties or version catalogue')
    if kind == 'cargo':
        packages = tomllib.loads((root / 'Cargo.lock').read_text())['package']
        versions = {item['version'] for item in packages if item['name'] == package}
        if len(versions) != 1:
            raise ValueError(f'{package} has multiple versions; select a project-specific profile')
        return versions.pop()
    if kind == 'go':
        # go.sum can contain obsolete dependencies; go.mod selects the graph.
        content = (root / 'go.mod').read_text()
        found = re.search(r'(?m)^\s*(?:require\s+)?' + re.escape(package) + r'\s+v(\d[^\s]*)', content)
        if found and not re.search(r'(?m)^\s*(?:replace\s+)?' + re.escape(package) + r'\s+[^\n]*=>', content):
            return found[1]
        raise ValueError(f'{package} is missing or replaced; use a project-specific profile')
    if kind == 'gem':
        content = (root / 'Gemfile.lock').read_text()
        versions = re.findall(r'(?m)^    ' + re.escape(package) + r' \(([^)]+)\)', content)
        if len(set(versions)) != 1:
            raise ValueError(f'{package} does not have one locked version')
        return versions[0]
    raise ValueError(f'unsupported metadata kind {kind}')


def check(kind, package, expected, root=Path('.')):
    actual = installed(kind, package, root)
    if actual.split('.')[:len(expected.split('.'))] != expected.split('.'):
        raise ValueError(f'{package}: selected profile {expected} does not match installed/locked {actual}')
    return actual


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if arguments and arguments[0] == '--node-pnp':
            print(next(at / '.pnp.cjs' for at in node_roots(Path('.')) if (at / '.pnp.cjs').is_file()))
        elif arguments and arguments[0] == '--node-manager':
            print(node_manager())
        elif arguments and arguments[0] == '--yarn-path':
            print(yarn_path())
        elif arguments and arguments[0] == '--node-modules':
            print(next(at / 'node_modules' for at in node_roots(Path('.')) if (at / 'node_modules').is_dir()))
        elif arguments and arguments[0] == '--node-bin':
            print(node_binary(arguments[1]))
        elif arguments and arguments[0] == '--detect':
            kind, package = arguments[1:]
            if kind == 'npm':
                values = node_locked(package, Path('.'))
                try:
                    values.add(installed(kind, package))
                except FileNotFoundError:
                    pass
                if not values:
                    return 3
                print(one_version(values, package))
                return 0
            if not has_metadata(kind):
                return 3
            if kind == 'composer' and not Path('vendor/composer/installed.json').exists():
                data = json.loads(Path('composer.lock').read_text())
                print(one_version((p['version'].lstrip('v') for p in data.get('packages', []) + data.get('packages-dev', []) if p['name'] == package), package))
            else:
                print(installed(kind, package))
        elif len(arguments) == 2:
            print(installed(*arguments))
        else:
            kind, package, expected = arguments
            check(kind, package, expected)
        return 0
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print(f'framework: {error}. Install the existing locked dependencies or select a matching profile; no dependencies were changed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
