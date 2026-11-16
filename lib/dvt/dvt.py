"""Generate a development flake without installing or editing application dependencies."""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

SYSTEMS = ("x86_64-linux", "aarch64-linux", "aarch64-darwin")
ALIASES = {"c": "c-cpp", "cpp": "c-cpp", "gha": "github-actions", "k8s": "kubernetes", "docs": "markdown", "md": "markdown", "js": "node", "sh": "shell", "tf": "terraform", "ts": "typescript"}


class InitError(Exception):
    pass


def nix_string(value):
    # JSON strings are also Nix strings, except for Nix interpolation.
    return json.dumps(value, ensure_ascii=False).replace("${", r"\${")


def generate(name, catalogue, framework_version=None, dev_input=None):
    name = ALIASES.get(name, name)
    frameworks = catalogue["frameworks"]
    if name in frameworks:
        profile = frameworks[name]
        version = framework_version or profile["defaultVersion"]
        if version not in profile["versions"]:
            raise InitError(f"unsupported {name} version {version!r}; supported: {', '.join(profile['versions'])}")
        selection = f"frameworks = [ {{ name = {nix_string(name)}; version = {nix_string(version)}; }} ];"
        description = f"Development tools for {name} {version}"
        notes = """          # Application checks use the existing environment, never Nix's framework.
          # Override with DVT_PROJECT_PYTHON or change this path.
          options.projectPython = ".venv/bin/python";
"""
        if "python" not in profile["languages"]:
            notes = ""
    elif name in catalogue["languages"]:
        if framework_version:
            raise InitError("--framework-version requires a framework, not a language")
        selection = f"languages = [ {nix_string(name)} ];"
        description = f"Development tools for {name}"
        notes = ""
    else:
        close = difflib.get_close_matches(name, [*frameworks, *catalogue["languages"], *ALIASES], n=3)
        hint = f" Did you mean {', '.join(close)}?" if close else ""
        raise InitError(f"unknown framework or language {name!r}.{hint} Run dvt list.")
    # Preserve the language's package-set requirements, e.g. unfree Hashi tools.
    languages = frameworks[name]["languages"] if name in frameworks else [name]
    config = list(dict.fromkeys(line for language in languages for line in catalogue["languages"][language].get("nixpkgsConfig", [])))
    config_text = "".join(f"          {line.replace('inputs.nixpkgs', 'nixpkgs')}\n" for line in config)
    flake = """{
  description = DESCRIPTION;
  inputs = {
    # Keep tooling locked independently from the application's dependencies.
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1";
    dev.url = DEV_INPUT;
  };
  outputs = { nixpkgs, dev, ... }:
    let
      systems = [ SYSTEMS ];
      eachSystem = nixpkgs.lib.genAttrs systems;
      project = system:
        let pkgs = import nixpkgs {
          inherit system;
CONFIG        };
        in dev.lib.mkProject {
          inherit pkgs;
          # Framework profiles inherit their language defaults.
          SELECTION
NOTES        };
    in {
      devShells = eachSystem (system: { default = (project system).devShell; });
      # Independently buildable commands for CI and other automation.
      packages = eachSystem (system: (project system).commands);
    };
}
"""
    substitutions = {"DESCRIPTION": nix_string(description), "DEV_INPUT": nix_string(dev_input or catalogue["devInput"]), "SYSTEMS": " ".join(map(nix_string, SYSTEMS)), "CONFIG": config_text, "SELECTION": selection, "NOTES": notes}
    flake = re.sub(r"\b(?:" + "|".join(substitutions) + r")\b", lambda match: substitutions[match[0]], flake)
    return {"flake.nix": flake, ".envrc": "use flake\nwatch_file flake.nix\nwatch_file flake.lock\n"}



def nix_value(value, level=0):
    indent = '  ' * level
    if isinstance(value, str):
        return nix_string(value)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, list):
        return '[ ' + ' '.join(nix_value(item, level + 1) for item in value) + ' ]'
    if isinstance(value, dict):
        return '{\n' + ''.join(indent + '  ' + nix_string(key) + ' = ' + nix_value(item, level + 1) + ';\n' for key, item in value.items()) + indent + '}'
    raise InitError(f'unsupported generated Nix value {value!r}')


def generate_discovered(plan, catalogue, dev_input=None):
    languages = {language for component in plan['components'].values() for language in component['languages']}
    languages |= {language for component in plan['components'].values() for framework in component['frameworks'] for language in catalogue['frameworks'][framework['name']]['languages']}
    config = list(dict.fromkeys(line.replace('inputs.nixpkgs', 'nixpkgs') for name in sorted(languages) for line in catalogue['languages'][name].get('nixpkgsConfig', [])))
    flake = '''{
  description = "Discovered project checks using existing configurations and dependencies";
  inputs.nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1";
  inputs.dev.url = DEV_INPUT;
  outputs = { nixpkgs, dev, ... }:
    let
      eachSystem = nixpkgs.lib.genAttrs [ SYSTEMS ];
      workspace = system: dev.lib.mkWorkspace {
        pkgs = import nixpkgs { inherit system; CONFIG };
        # Review with dvt inspect. Commands load the original project configs.
        components = COMPONENTS;
      };
    in {
      devShells = eachSystem (system: (workspace system).devShells);
      packages = eachSystem (system: (workspace system).commands);
    };
}
'''
    substitutions = {'DEV_INPUT': nix_string(dev_input or catalogue['devInput']), 'SYSTEMS': ' '.join(map(nix_string, SYSTEMS)), 'CONFIG': ' '.join(config), 'COMPONENTS': nix_value(plan['components'], 4)}
    flake = re.sub(r'\b(?:' + '|'.join(substitutions) + r')\b', lambda match: substitutions[match[0]], flake)
    return {'flake.nix': flake, '.envrc': 'use flake\nwatch_file flake.nix\nwatch_file flake.lock\n'}


def detect_version(name, directory, catalogue):
    """Read existing metadata, never import application code or resolve packages."""
    profile = catalogue['frameworks'].get(name)
    if profile is None:
        return None
    root = Path(directory)
    versions = set()
    if profile.get('kind') == 'flutter':
        fvm = root / '.fvmrc'
        if fvm.exists():
            actual = json.loads(fvm.read_text()).get('flutter', '')
            if re.fullmatch(r'\d+\.\d+\.\d+', actual):
                versions.add(actual)
    elif 'distribution' in profile:
        package = profile['distribution'].lower().replace('_', '-')
        for filename in ('uv.lock', 'poetry.lock'):
            path = root / filename
            if path.exists():
                for item in tomllib.loads(path.read_text()).get('package', []):
                    if item.get('name', '').lower().replace('_', '-') == package:
                        versions.add(item['version'])
        lock = root / 'Pipfile.lock'
        if lock.exists():
            data = json.loads(lock.read_text())
            for section in ('default', 'develop'):
                value = data.get(section, {}).get(package, {}).get('version', '')
                if value.startswith('=='):
                    versions.add(value[2:])
        requirements = root / 'requirements.txt'
        if requirements.exists():
            versions.update(re.findall(r'(?im)^' + re.escape(package) + r'==([0-9][^\s;#]*)', requirements.read_text()))
        # Existing installed metadata is useful when a project uses an unsupported
        # lock format. It is read as text, without starting its interpreter.
        if not versions:
            for metadata in root.glob('.venv/lib/python*/site-packages/*.dist-info/METADATA'):
                content = metadata.read_text()
                found_name = re.search(r'(?m)^Name: (.+)$', content)
                found_version = re.search(r'(?m)^Version: (.+)$', content)
                if found_name and found_version and found_name[1].strip().lower().replace('_', '-') == package:
                    versions.add(found_version[1].strip())
    elif profile.get('adapter') == 'node':
        if catalogue.get('versionReader'):
            result = subprocess.run([sys.executable, '-I', catalogue['versionReader'], '--detect', 'npm', profile['package']], cwd=root, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                versions.add(result.stdout.strip())
            elif result.returncode != 3:
                raise InitError(f'{name}: conflicting or invalid dependency metadata: {result.stderr.strip()}')
        installed = root / 'node_modules' / profile['package'] / 'package.json'
        if installed.exists():
            versions.add(json.loads(installed.read_text())['version'])
        lock = root / 'package-lock.json'
        if lock.exists():
            data = json.loads(lock.read_text())
            entry = data.get('packages', {}).get('node_modules/' + profile['package'], {})
            entry = entry or data.get('dependencies', {}).get(profile['package'], {})
            if 'version' in entry:
                versions.add(entry['version'])
    elif catalogue.get('versionReader') and root.is_dir() and profile.get('kind') != 'flutter':
        packages = {profile['package']} | {v.get('package', profile['package']) for v in profile.get('variants', {}).values()}
        failures = []
        for package in sorted(packages):
            result = subprocess.run([sys.executable, '-I', catalogue['versionReader'], '--detect', profile['kind'], package], cwd=root, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                versions.add(result.stdout.strip())
            elif result.returncode != 3:
                failures.append(result.stderr.strip())
        if failures and not versions:
            raise InitError(f'{name}: cannot determine a compatible version from existing metadata: ' + '; '.join(failures))
    if len(versions) > 1:
        raise InitError(f'{name} has conflicting dependency versions {sorted(versions)}; select --framework-version explicitly')
    if not versions:
        return None
    actual = versions.pop()
    matching = [line for line in profile['versions'] if actual.split('.')[:len(line.split('.'))] == line.split('.')]
    if not matching:
        raise InitError(f'{name} {actual} is not covered by a profile; supported release lines: {", ".join(profile["versions"])}')
    return max(matching, key=len)


def write_files(directory, files):
    directory = Path(directory)
    # Refuse the entire operation before creating any file. Never overwrite
    # an existing flake or direnv configuration, including dangling symlinks.
    conflicts = [name for name in files if os.path.lexists(directory / name)]
    if conflicts:
        raise InitError("existing files would be overwritten: " + ", ".join(conflicts) + "; use --dry-run to review and merge manually")
    directory.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for name, content in files.items():
            with (directory / name).open("x", encoding="utf-8") as handle:
                created.append(directory / name)
                handle.write(content)
    except OSError:
        for path in created:
            path.unlink()
        raise


def main(argv=None, catalogue=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    describe = sub.add_parser("describe", help="show a framework profile or the researched coverage for a language")
    describe.add_argument("name")
    listing = sub.add_parser("list", help="list supported languages, frameworks and framework versions")
    listing.add_argument("--json", action="store_true", help="machine-readable registry, coverage counts and validation levels")
    init = sub.add_parser("init", help="generate a flake for a framework or language")
    init.add_argument("name", nargs="?", help="framework/language; omit to discover the existing workspace")
    init.add_argument("--exclude", action="append", default=[], help="exclude a repository-relative subtree from discovery (repeatable)")
    inspect = sub.add_parser("inspect", help="report detected project components, versions, configurations and commands without writing")
    inspect.add_argument("--directory", "-d", default=".")
    inspect.add_argument("--exclude", action="append", default=[])
    init.add_argument("--framework-version", help="framework release line; otherwise detect existing metadata or use the listed default")
    init.add_argument("--directory", "-d", default=".")
    init.add_argument("--dev-input", help="override the pinned dev flake reference (e.g. path:/checkout)")
    init.add_argument("--dry-run", action="store_true", help="print generated files as JSON without writing")
    args = parser.parse_args(argv)
    if catalogue is None:
        with open(os.environ["DVT_CATALOGUE"], encoding="utf-8") as handle:
            catalogue = json.load(handle)
    try:
        if args.command == "inspect" or (args.command == "init" and args.name is None):
            from discovery import discover
            if args.command == "init" and args.framework_version:
                raise InitError('--framework-version requires an explicit framework name')
            plan = discover(args.directory, catalogue, detect_version, args.exclude)
            if args.command == "inspect":
                print(json.dumps(plan, indent=2))
                return 0
            files = generate_discovered(plan, catalogue, args.dev_input)
            if args.dry_run:
                print(json.dumps(files, indent=2))
            else:
                write_files(args.directory, files)
                print(f'Created flake.nix and .envrc for {len(plan["components"])} project components. Existing tool configurations and dependencies were preserved.')
                for item in plan['detected']:
                    print(f'  {item["root"]}: ' + ', '.join(item['languages']) + '; frameworks: ' + (', '.join(p['name'] + ' ' + p['version'] for p in item['frameworks']) or 'language defaults'))
                for warning in plan['warnings']:
                    print('Unassigned configuration: ' + warning)
                print('Commands: quality, style, security, architecture, tests. Review discovery with dvt inspect.')
            return 0
        if args.command == "describe":
            name = ALIASES.get(args.name, args.name)
            coverage = catalogue.get("coverage", {}).get("languages", {})
            if name in catalogue["frameworks"]:
                print(json.dumps(catalogue["frameworks"][name], indent=2))
                return 0
            if name not in coverage:
                raise InitError(f"no language coverage entry for {name!r}")
            entry = dict(coverage[name])
            entry["available_profiles"] = {key: value["versions"] for key, value in catalogue["frameworks"].items() if name in value["languages"]}
            print(json.dumps(entry, indent=2))
            return 0
        if args.command == "list":
            stats = {
                "frameworks": len(catalogue["frameworks"]),
                "release_lines": sum(len(p["versions"]) for p in catalogue["frameworks"].values()),
                "languages_with_profiles": len({language for p in catalogue["frameworks"].values() for language in p["languages"]}),
                "language_defaults": len(catalogue["languages"]),
            }
            if args.json:
                print(json.dumps({"counts": stats, "frameworks": catalogue["frameworks"], "languages": sorted(catalogue["languages"])}, indent=2))
                return 0
            print(f'{stats["frameworks"]} framework profiles, {stats["release_lines"]} release lines, {stats["languages_with_profiles"]} language modules with profiles; {stats["language_defaults"]} language defaults.')
            print("Frameworks:")
            for name, profile in sorted(catalogue["frameworks"].items()):
                print(f"  {name}: {', '.join(profile['versions'])} (default {profile['defaultVersion']}; {profile.get('validation', 'custom')})")
            print("Languages:\n  " + ", ".join(sorted(catalogue["languages"])))
            return 0
        name = ALIASES.get(args.name, args.name)
        version = args.framework_version or detect_version(name, args.directory, catalogue)
        files = generate(name, catalogue, version, args.dev_input)
        if args.dry_run:
            print(json.dumps(files, indent=2))
        else:
            write_files(args.directory, files)
            print(f"Created flake.nix and .envrc in {Path(args.directory).absolute()}")
            print("Keep using your existing dependency manager. Add the generated files to git, enter nix develop, and commit flake.lock.")
            print("Commands: quality, style, security, architecture, tests. CI: style --check.")
            print("architecture uses existing tool configuration; architecture.toml is optional.")
        return 0
    except (InitError, OSError, ValueError, KeyError) as error:
        print(f"dvt: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
