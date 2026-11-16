{
  pkgs,
  lib,
  dev,
}:
let
  configured = {
    quality = [
      {
        runner = "node";
        argv = [
          "eslint"
          "."
        ];
      }
    ];
    style = [
      {
        runner = "node";
        argv = [
          "prettier"
          "--write"
          "."
        ];
      }
    ];
    security = [
      {
        runner = "node";
        argv = [
          "custom-sast"
          "--config"
          "sast.json"
        ];
      }
    ];
    architecture = [
      {
        runner = "node";
        argv = [
          "depcruise"
          "--config"
          ".dependency-cruiser.cjs"
          "."
        ];
      }
    ];
    tests = [
      {
        runner = "node";
        argv = [
          "vitest"
          "run"
        ];
      }
    ];
  };
  project = dev.mkProject {
    inherit pkgs configured;
    languages = [ "node" ];
  };
  scripts = lib.mapAttrs (
    name: text:
    pkgs.writeShellApplication {
      inherit name text;
      runtimeInputs = [
        pkgs.coreutils
        pkgs.rsync
        pkgs.gnugrep
      ];
      excludeShellChecks = [ "SC2329" ];
    }
  ) project.texts;
  pythonProject = dev.mkProject {
    inherit pkgs;
    languages = [ "python" ];
    configured.architecture = [
      {
        runner = "python";
        argv = [ "lint-imports" ];
      }
    ];
  };
  pythonCommand = pkgs.writeShellApplication {
    name = "python-architecture";
    text = pythonProject.texts.architecture;
    runtimeInputs = [
      pkgs.coreutils
      pkgs.rsync
      pkgs.gnugrep
    ];
    excludeShellChecks = [ "SC2329" ];
  };
  projectTests = pkgs.writeShellApplication {
    name = "project-tests";
    text = pythonProject.texts.tests;
    runtimeInputs = [ pkgs.coreutils ];
    excludeShellChecks = [ "SC2329" ];
  };
  runtime = import ./import-linter.nix { inherit pkgs; };
  absent = pkgs.writeShellApplication {
    name = "no-architecture";
    text =
      (dev.mkProject {
        inherit pkgs;
        languages = [ "empty" ];
      }).texts.architecture;
    excludeShellChecks = [ "SC2329" ];
  };
in
assert lib.assertMsg (
  !(lib.hasInfix "--config auto" project.texts.security)
) "Configured SAST was replaced with automatic rules";
assert lib.assertMsg (
  !(lib.hasInfix "run oxlint" project.texts.quality)
) "Configured quality inherited another checker";
pkgs.runCommand "configured-project-checks"
  {
    nativeBuildInputs = [
      pkgs.coreutils
      pkgs.gnugrep
    ];
  }
  ''
    export DVT_CONFIGURED_LOG="$TMPDIR/commands.log"
    mkdir node node/node_modules node/node_modules/.bin
    cd node
    echo '{"private":true}' > package.json
    echo 'module.exports = { forbidden: [] };' > .dependency-cruiser.cjs
    echo '{"rules":[]}' > sast.json
    cat > node_modules/.bin/tool <<'SH'
    #!${pkgs.bash}/bin/bash
    set -euo pipefail
    printf '%s\n' "$(basename "$0") $*" >> "$DVT_CONFIGURED_LOG"
    case "$(basename "$0")" in
      prettier) if [ "''${DVT_FORMAT_WRITE:-0}" = 1 ]; then echo formatted > source.txt; fi ;;
      depcruise) test "$1" = --config; test -f "$2" ;;
      custom-sast) test "$1" = --config; test -f "$2" ;;
    esac
    exit "''${DVT_TOOL_FAIL:-0}"
    SH
    chmod +x node_modules/.bin/tool
    for name in eslint prettier custom-sast depcruise vitest; do ln -s tool node_modules/.bin/$name; done
    ${lib.concatStrings (
      lib.mapAttrsToList (name: command: ''
        ${command}/bin/${name} > ${name}.log 2>&1 || { cat ${name}.log; exit 1; }
        export DVT_TOOL_FAIL=1
        if ${command}/bin/${name} > failed.log 2>&1; then echo '${name} ignored project tool failure'; exit 1; fi
        unset DVT_TOOL_FAIL
      '') scripts
    )}
    echo original > source.txt
    ${scripts.style}/bin/style --check > "$TMPDIR/style-check.log" 2>&1 || { cat "$TMPDIR/style-check.log"; exit 1; }
    export DVT_FORMAT_WRITE=1
    if ${scripts.style}/bin/style --check > "$TMPDIR/style-change.log" 2>&1; then echo 'formatting difference passed'; exit 1; fi
    grep 'style would change' "$TMPDIR/style-change.log"
    grep '^original$' source.txt
    unset DVT_FORMAT_WRITE
    grep 'depcruise --config .dependency-cruiser.cjs .' "$DVT_CONFIGURED_LOG"
    test ! -f architecture.toml
    rm node_modules/.bin/depcruise
    if ${scripts.architecture}/bin/architecture > missing.log 2>&1; then echo 'missing project tool passed'; exit 1; fi
    grep 'missing; no dependency was added' missing.log
    cd ..
    mkdir python
    cd python
    export DVT_PROJECT_PYTHON=${runtime}/bin/python
    # Tests must use the same project interpreter even when only architecture
    # was explicitly configured. A foreign interpreter has no pytest here.
    mkdir tests .venv .venv/bin
    cat > .venv/bin/python <<'SH'
    #!${pkgs.bash}/bin/bash
    test "$1" = -m && test "$2" = pytest
    SH
    chmod +x .venv/bin/python
    DVT_PROJECT_PYTHON="$PWD/.venv/bin/python" ${projectTests}/bin/project-tests
    mkdir example
    echo > example/__init__.py
    echo > example/outer.py
    echo > example/inner.py
    cat > .importlinter <<'INI'
    [importlinter]
    root_package = example
    [importlinter:contract:boundaries]
    name = inner cannot use outer
    type = forbidden
    source_modules = example.inner
    forbidden_modules = example.outer
    INI
    # Real import-linter enforces the project's own contract without architecture.toml.
    ${pythonCommand}/bin/python-architecture > pass.log 2>&1 || { cat pass.log; exit 1; }
    echo 'import example.outer' > example/inner.py
    if ${pythonCommand}/bin/python-architecture > fail.log 2>&1; then cat fail.log; echo 'architecture violation passed'; exit 1; fi
    grep -i broken fail.log
    mkdir ../empty
    cd ../empty
    code=0
    ${absent}/bin/no-architecture > absent.log 2>&1 || code=$?
    test "$code" -eq 2
    grep 'no configured architecture check' absent.log
    touch $out
  ''
