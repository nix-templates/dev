"""Inspect existing files without importing application code or resolving packages."""
import fnmatch
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path

CATEGORIES = ('quality', 'style', 'security', 'architecture', 'tests')
MANIFESTS = {
    'package.json', 'pyproject.toml', 'setup.py', 'requirements.txt', 'Pipfile',
    'Gemfile', 'composer.json', 'Cargo.toml', 'go.mod', 'pom.xml', 'build.gradle',
    'build.gradle.kts', 'mix.exs', 'rebar.config', 'shard.yml', 'renv.lock',
    'DESCRIPTION', 'Project.toml', 'pubspec.yaml', 'CMakeLists.txt', 'project.clj',
    'deps.edn', 'gleam.toml', 'deno.json', 'deno.jsonc', 'elm.json', 'build.zig',
    'dune-project', 'stack.yaml', 'cabal.project', 'cpanfile', 'fpm.toml',
    'lakefile.toml', 'lakefile.lean', 'spago.yaml', 'platformio.ini', 'Pulumi.yaml',
}
# More specific hosts take precedence over their underlying libraries; all
# discoveries remain in the report. Independent language families are composed.
PRIORITY = ['nextjs', 'nuxt', 'sveltekit', 'angular', 'astro', 'docusaurus', 'vitepress',
            'nestjs', 'fastify', 'express', 'hono', 'react', 'vue', 'svelte',
            'django', 'fastapi', 'flask', 'litestar', 'starlette', 'rails', 'hanami',
            'phoenix', 'liveview', 'ash', 'laravel', 'symfony', 'serverpod', 'flutter',
            'qt', 'drogon', 'catch2', 'googletest']
EXCLUDE = ['.git', '.direnv', '.venv', '.tox', '.nox', '.cache', '.yarn', '.pnpm-store',
           '.dart_tool', '.next', '.nuxt', '.output', '.svelte-kit', 'venv', 'coverage']


def json_file(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def toml_file(path):
    return tomllib.loads(path.read_text()) if path.is_file() else {}


def configured_tools(root):
    """Keep native configs intact and build argv for the tools that own them."""
    result, evidence = {}, []
    package = json_file(root / 'package.json')
    composer = json_file(root / 'composer.json')
    pyproject = toml_file(root / 'pyproject.toml')
    pytools = pyproject.get('tool', {})

    def add(category, runner, argv, source, **extra):
        entry = {'runner': runner, 'argv': argv, **extra}
        if entry not in result.setdefault(category, []):
            result[category].append(entry)
            evidence.append({'category': category, 'source': source, 'command': entry})

    def matching(*patterns):
        return sorted({p.name for pattern in patterns for p in root.glob(pattern) if p.is_file()})

    # Existing explicit category scripts are authoritative. Conventional package
    # script names are recognized but the public interface remains canonical.
    script_names = {'quality': ('quality', 'check', 'lint'), 'style': ('style', 'format', 'fmt'),
                    'security': ('security', 'audit'), 'architecture': ('architecture',), 'tests': ('tests', 'test')}
    authoritative = set()
    for manifest, data, runner in [('package.json', package, 'script'), ('composer.json', composer, 'composer')]:
        scripts = data.get('scripts', {})
        for category, names in script_names.items():
            chosen = next((name for name in names if name in scripts), None)
            if chosen:
                add(category, runner, [chosen], f'{manifest}:scripts.{chosen}')
                authoritative.add(category)

    # Tool options retain their configuration file and the project's installed plugins.
    definitions = [
        ('quality', 'node', ['eslint', '.'], ('eslint.config.*', '.eslintrc*'), 'eslintConfig'),
        ('quality', 'node', ['biome', 'check', '.'], ('biome.json', 'biome.jsonc'), None),
        ('style', 'node', ['biome', 'format', '--write', '.'], ('biome.json', 'biome.jsonc'), None),
        ('style', 'node', ['prettier', '--write', '--ignore-unknown', '.'], ('.prettierrc*', 'prettier.config.*'), 'prettier'),
        ('quality', 'node', ['stylelint', '**/*.{css,scss,less,vue}'], ('.stylelintrc*', 'stylelint.config.*'), 'stylelint'),
        ('architecture', 'node', ['depcruise', '--config', '$config', 'src' if (root / 'src').is_dir() else '.'], ('.dependency-cruiser.*', 'dependency-cruiser.config.*'), None),
        ('architecture', 'node', ['knip', '--no-progress'], ('knip.*', '.knip.*'), 'knip'),
        ('quality', 'python', ['ruff', 'check', '.'], ('ruff.toml', '.ruff.toml'), 'ruff'),
        ('style', 'python', ['ruff', 'format', '.'], ('ruff.toml', '.ruff.toml'), 'ruff'),
        ('quality', 'python', ['mypy', '.'], ('mypy.ini', '.mypy.ini'), 'mypy'),
        ('quality', 'python', ['pylint', '.'], ('.pylintrc', 'pylintrc'), 'pylint'),
        ('style', 'python', ['black', '.'], (), 'black'),
        ('style', 'python', ['isort', '.'], ('.isort.cfg',), 'isort'),
        ('architecture', 'python', ['lint-imports'], ('.importlinter',), 'importlinter'),
        ('architecture', 'python', ['deptry', '.'], (), 'deptry'),
        ('tests', 'python', ['pytest'], ('pytest.ini', '.pytest.ini'), 'pytest'),
        ('quality', 'php', ['vendor/bin/phpstan', 'analyse', '--no-progress'], ('phpstan.neon', 'phpstan.neon.dist'), None),
        ('quality', 'php', ['vendor/bin/psalm', '--no-progress'], ('psalm.xml', 'psalm.xml.dist'), None),
        ('quality', 'php', ['vendor/bin/phpcs'], ('phpcs.xml', 'phpcs.xml.dist', '.phpcs.xml'), None),
        ('style', 'php', ['vendor/bin/php-cs-fixer', 'fix', '.'], ('.php-cs-fixer.php', '.php-cs-fixer.dist.php'), None),
        ('architecture', 'php', ['vendor/bin/deptrac', 'analyse', '--no-progress'], ('deptrac.yaml', 'deptrac.yml'), None),
        ('tests', 'php', ['vendor/bin/phpunit'], ('phpunit.xml', 'phpunit.xml.dist'), None),
        ('quality', 'ruby', ['rubocop', '--fail-level', 'warning'], ('.rubocop.yml',), None),
        ('style', 'ruby', ['rubocop', '--autocorrect-all', '--fail-level', 'fatal'], ('.rubocop.yml',), None),
        ('architecture', 'ruby', ['packwerk', 'check'], ('packwerk.yml',), None),
        ('tests', 'ruby', ['rspec'], ('.rspec',), None),
        ('security', 'environment', ['semgrep', 'scan', '--config', '$config', '--error', '.'], ('.semgrep.yml', '.semgrep.yaml', 'semgrep.yml', 'semgrep.yaml'), None),
        ('security', 'environment', ['gitleaks', 'dir', '.', '--config', '$config', '--no-banner', '--redact'], ('.gitleaks.toml', 'gitleaks.toml'), None),
        ('security', 'environment', ['trivy', '--config', '$config', 'fs', '--exit-code', '1', '.'], ('trivy.yaml', 'trivy.yml'), None),
        ('quality', 'environment', ['golangci-lint', 'run'], ('.golangci.yml', '.golangci.yaml', '.golangci.toml', '.golangci.json'), None),
        ('security', 'environment', ['cargo', 'deny', '--locked', 'check'], ('deny.toml',), None),
        ('architecture', 'environment', ['cargo', 'deny', '--locked', 'check', 'bans'], ('deny.toml',), None),
        ('quality', 'environment', ['luacheck', '.'], ('.luacheckrc',), None),
        ('quality', 'environment', ['selene', '.'], ('selene.toml',), None),
        ('style', 'environment', ['stylua', '.'], ('stylua.toml', '.stylua.toml'), None),
        ('tests', 'environment', ['busted'], ('.busted',), None),
        ('quality', 'environment', ['hlint', '.'], ('.hlint.yaml',), None),
        ('architecture', 'environment', ['weeder'], ('weeder.toml',), None),
        ('quality', 'environment', ['scalafmt', '--test'], ('.scalafmt.conf',), None),
        ('style', 'environment', ['scalafmt'], ('.scalafmt.conf',), None),
        ('quality', 'environment', ['scalafix', '--check'], ('.scalafix.conf',), None),
        ('quality', 'environment', ['ameba'], ('.ameba.yml',), None),
        ('quality', 'environment', ['swiftlint', 'lint', '--strict'], ('.swiftlint.yml',), None),
        ('style', 'environment', ['swiftformat', '.'], ('.swiftformat',), None),
        ('architecture', 'environment', ['periphery', 'scan', '--strict', '--skip-build'], ('.periphery.yml',), None),
        ('quality', 'python', ['sqlfluff', 'lint'], ('.sqlfluff',), None),
        ('style', 'python', ['sqlfluff', 'format'], ('.sqlfluff',), None),
        ('security', 'environment', ['checkov', '--config-file', '$config', '--directory', '.'], ('.checkov.yml', '.checkov.yaml'), None),
    ]
    for category, runner, argv, patterns, key in definitions:
        if category in authoritative:
            continue
        paths = matching(*patterns)
        inline = key is not None and key in (pytools if runner == 'python' else package)
        if paths or inline:
            # Multiple variant configs are ambiguous to us; let tools with native
            # discovery pick. Explicit --config tools need one unambiguous file.
            if '$config' in argv and len(paths) != 1:
                raise ValueError(f'{root}: multiple configurations for {argv[0]}: {paths}; define a canonical category script to select one')
            args = [paths[0] if arg == '$config' else arg for arg in argv]
            add(category, runner, args, paths[0] if paths else f'{"pyproject.toml:tool" if runner == "python" else "package.json"}.{key}')

    if 'security' not in authoritative:
        if 'bandit' in pytools:
            add('security', 'python', ['bandit', '-r', '.', '-c', 'pyproject.toml'], 'pyproject.toml:tool.bandit')
        elif (root / '.bandit').is_file():
            add('security', 'python', ['bandit', '-r', '.', '--ini', '.bandit'], '.bandit')
        if (root / '.semgrep').is_dir() and not any(x['argv'][0] == 'semgrep' for x in result.get('security', [])):
            add('security', 'environment', ['semgrep', 'scan', '--config', '.semgrep', '--error', '.'], '.semgrep/')
    # Framework compilers own their template/macro semantics. Never invoke a
    # helper that offers an automatic install unless its required tool exists.
    if 'quality' not in authoritative:
        if (root / 'angular.json').is_file():
            add('quality', 'node', ['ng', 'build', '--configuration', 'development', '--progress=false'], 'angular.json')
        elif matching('nuxt.config.*'):
            add('quality', 'node', ['nuxt', 'typecheck'], matching('nuxt.config.*')[0], requires=['vue-tsc'])
        elif matching('svelte.config.*'):
            if '@sveltejs/kit' in package.get('devDependencies', {}) or '@sveltejs/kit' in package.get('dependencies', {}):
                add('quality', 'node', ['svelte-kit', 'sync'], matching('svelte.config.*')[0])
            add('quality', 'node', ['svelte-check', '--fail-on-warnings'], matching('svelte.config.*')[0])
        elif matching('astro.config.*'):
            add('quality', 'node', ['astro-check'], matching('astro.config.*')[0])
        elif (root / 'tsconfig.json').is_file():
            dependency_names = set(package.get('dependencies', {})) | set(package.get('devDependencies', {}))
            add('quality', 'node', ['vue-tsc' if 'vue' in dependency_names else 'tsc', '--noEmit'], 'tsconfig.json')

    build = '\n'.join((root / f).read_text() for f in ('build.gradle', 'build.gradle.kts', 'pom.xml') if (root / f).is_file())
    if (root / 'gradlew').is_file():
        for category, identifier, argv in [
            ('quality', 'io.gitlab.arturbosch.detekt', ['detekt']),
            ('quality', 'checkstyle', ['checkstyleMain']), ('quality', 'pmd', ['pmdMain']),
            ('quality', 'com.github.spotbugs', ['spotbugsMain']),
            ('style', 'com.diffplug.spotless', ['spotlessApply']),
            ('architecture', 'com.autonomousapps.dependency-analysis', ['buildHealth']),
            ('architecture', 'archunit', ['test']),
        ]:
            if identifier in build and category not in authoritative:
                add(category, 'gradle', argv, 'build.gradle(.kts)')
    elif (root / 'mvnw').is_file():
        for category, identifier, argv in [
            ('quality', 'maven-checkstyle-plugin', ['checkstyle:check']),
            ('quality', 'maven-pmd-plugin', ['pmd:check']), ('quality', 'spotbugs-maven-plugin', ['spotbugs:check']),
            ('style', 'spotless-maven-plugin', ['spotless:apply']),
            ('architecture', 'maven-enforcer-plugin', ['enforcer:enforce']), ('architecture', 'archunit', ['test']),
        ]:
            if identifier in build and category not in authoritative:
                add(category, 'maven', argv, 'pom.xml')
    return result, evidence


def dependency_candidates(root, registry, reader_path):
    package = json_file(root / 'package.json')
    node = set().union(*(set(package.get(key, {})) for key in ('dependencies', 'devDependencies', 'peerDependencies')))
    pyproject = toml_file(root / 'pyproject.toml')
    python = set(pyproject.get('tool', {}).get('poetry', {}).get('dependencies', {}))
    pipfile = toml_file(root / 'Pipfile')
    python.update(pipfile.get('packages', {}))
    python.update(pipfile.get('dev-packages', {}))
    requirements = list(pyproject.get('project', {}).get('dependencies', []))
    for values in pyproject.get('project', {}).get('optional-dependencies', {}).values():
        requirements.extend(values)
    if (root / 'requirements.txt').is_file():
        requirements.extend((root / 'requirements.txt').read_text().splitlines())
    for value in requirements:
        match = re.match(r'\s*([A-Za-z0-9_.-]+)', value)
        if match:
            python.add(match[1])
    if not python:
        for name in ('uv.lock', 'poetry.lock'):
            for entry in toml_file(root / name).get('package', []):
                python.add(entry['name'])
    python = {name.lower().replace('_', '-') for name in python}
    # Other ecosystems use the version reader's known metadata files. Reading
    # text identifies candidates; the reader must still verify the actual version.
    module_spec = importlib.util.spec_from_file_location('dvt_versions', reader_path)
    reader = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(reader)
    texts = {}
    for name, profile in registry.items():
        if 'distribution' in profile:
            if profile['distribution'].lower().replace('_', '-') in python:
                yield name
        elif profile.get('adapter') == 'node':
            if profile['package'] in node:
                yield name
        elif profile.get('kind') == 'flutter':
            if (root / 'pubspec.yaml').is_file() and re.search(r'^\s*flutter:', (root / 'pubspec.yaml').read_text(), re.MULTILINE):
                yield name
        else:
            kind = profile.get('kind')
            if kind not in texts:
                manifest_names = {'gem': ['Gemfile'], 'composer': ['composer.json'], 'shards': ['shard.yml'], 'pub': ['pubspec.yaml'], 'cpan': ['cpanfile']}
                paths = {p for pattern in reader.METADATA.get(kind, []) + manifest_names.get(kind, []) for p in root.glob(pattern) if p.is_file()}
                texts[kind] = '\n'.join(p.read_text() for p in sorted(paths))
            packages = ({'qt', 'qtbase'} if profile['package'] == 'qt' else {profile['package']}) | {v.get('package', profile['package']) for v in profile.get('variants', {}).values()}
            if (kind == 'dotnet' and 'Microsoft.NET.Sdk.Web' in texts[kind]) or any(re.search(r'(?<![A-Za-z0-9_-])' + re.escape(p) + r'(?![A-Za-z0-9_-])', texts[kind]) for p in packages) or (profile.get('recipe') == 'jvm' and re.search(re.escape(name.replace('-', '')) + r'[._-]?[Vv]ersion', texts[kind].replace('-', ''))):
                yield name


def discover(directory, catalogue, detect_version, exclude=()):
    sys.path[:0] = catalogue.get('readerPaths', [])
    from ci import detect
    from layers import cli
    from layers.walk import walk
    root = Path(directory).resolve()
    if not root.is_dir():
        raise ValueError(f'{root} does not exist; name a framework or language to initialize a new project')
    files = walk(str(root), [*EXCLUDE, *('**/' + name for name in EXCLUDE), *exclude], hidden=True)
    # Symlinked sources/configuration outside the checkout are not auto-adopted.
    files = [name for name in files if (root / name).resolve().is_relative_to(root)]
    roots = {'.'} | {str(Path(name).parent) for name in files if Path(name).name in MANIFESTS or fnmatch.fnmatch(name, '*.csproj') or fnmatch.fnmatch(name, '*.fsproj') or fnmatch.fnmatch(name, '*.cabal')}
    components, report, warnings = {}, [], []
    ordered = sorted(roots, key=lambda value: (len(Path(value).parts), value), reverse=True)
    for location in sorted(roots):
        owned = [name for name in files if next((r for r in ordered if r == '.' or name.startswith(r + '/')), '.') == location]
        relative = [str(Path(name).relative_to(location)) for name in owned]
        at = root / location
        languages = set(detect.among(relative, cli.read_by(str(at), relative), catalogue['marks']))
        found = list(dependency_candidates(at, catalogue['frameworks'], catalogue['versionReader']))
        found.sort(key=lambda name: (PRIORITY.index(name) if name in PRIORITY else len(PRIORITY), name))
        selected, claimed = [], set()
        subsumes = {
            'nextjs': {'react'}, 'docusaurus': {'react'}, 'nuxt': {'vue'}, 'vitepress': {'vue'},
            'sveltekit': {'svelte'}, 'fastapi': {'starlette'}, 'nestjs': {'express', 'fastify'},
            'phoenix': {'liveview', 'ash'}, 'rails': {'sinatra', 'roda'}, 'hanami': {'roda'},
            'qt': {'catch2', 'googletest'}, 'drogon': {'catch2', 'googletest'},
        }
        for name in found:
            profile = catalogue['frameworks'][name]
            if claimed.intersection(profile['languages']):
                hosts = [entry['name'] for entry in selected if name in subsumes.get(entry['name'], set())]
                if hosts:
                    continue
                warnings.append(f'{location}: {name} overlaps another selected framework; its profile was not composed automatically. Review the discovered frameworks and use a custom profile for combined behavior.')
                continue
            version = detect_version(name, at, catalogue)
            if version is None:
                raise ValueError(f'{location}: detected {name} but no exact installed/locked version; install the existing locked environment or use an explicit dvt init {name} --framework-version selection')
            selected.append({'name': name, 'version': version})
            claimed.update(profile['languages'])
        configured, evidence = configured_tools(at)
        if not languages and not selected and not configured:
            continue
        runner_languages = {'node': 'node', 'script': 'node', 'composer': 'php', 'php': 'php', 'ruby': 'ruby', 'python': 'python', 'gradle': 'java', 'maven': 'java'}
        for specs in configured.values():
            for spec in specs:
                language = runner_languages.get(spec['runner'])
                if language and not (language == 'node' and 'typescript' in languages):
                    languages.add(language)
        languages -= claimed
        component = {'root': location, 'languages': sorted(languages), 'frameworks': selected, 'configured': configured}
        if any(spec['runner'] == 'python' for specs in configured.values() for spec in specs) or 'python' in claimed:
            component['options'] = {'projectPython': '.venv/bin/python'}
        component['enabledCommands'] = [name for name in CATEGORIES if name != 'architecture' or name in configured or (at / 'architecture.toml').is_file()]
        key = 'root' if location == '.' else location
        if key in components:
            key = './' + key
        components[key] = component
        report.append({'root': location, 'languages': sorted(languages | claimed), 'frameworks': selected, 'detectedFrameworks': found, 'tools': evidence, 'builtinArchitecture': (at / 'architecture.toml').is_file()})
        for path in ('tox.ini', 'noxfile.py', '.pre-commit-config.yaml'):
            if (at / path).is_file():
                warnings.append(f'{location}/{path}: environment-creating task configuration was preserved; it was not automatically assigned to a check category')
    if not components:
        raise ValueError('No supported source or project configuration was found; name a language explicitly')
    return {'components': components, 'detected': report, 'warnings': warnings}
