# The library behind the templates.
#
# A project takes this repository as a flake input and calls `mkProject` with
# its own pkgs and the languages it is written in. The tools and the commands
# `lint`, `fmt`, `scan`, `arch` and `tests` then come from the one definition
# here, so `nix flake update` brings every improvement to every project.
{ lib }:
let
  helpers = builtins.readFile ./helpers.sh;

  # Every file in languages/ is a language, named after the file.
  languages =
    lib.mapAttrs'
      (file: _: lib.nameValuePair (lib.removeSuffix ".nix" file) (import (./languages + "/${file}")))
      (
        lib.filterAttrs (
          file: type: type == "regular" && lib.hasSuffix ".nix" file && file != "common.nix"
        ) (builtins.readDir ./languages)
      );

  # The rules in a repository's architecture.toml. With no arguments it prints
  # the machine's hardware name, as the `arch` of coreutils does.
  arch =
    pkgs:
    pkgs.writeShellApplication {
      name = "arch";
      runtimeInputs = [
        pkgs.python3
        pkgs.git
      ];
      text = ''
        PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=${./arch} exec python3 -m arch "$@"
      '';
    };

  mkProject =
    {
      # The project's own package set, so tools match what the project builds with.
      pkgs,
      # Names from `languages`, paths to modules of your own, or the modules themselves.
      languages ? [ ],
      # The source tree, for `checks`. In a flake this is `self`.
      src ? null,
      # More packages for the shell and the commands' PATH.
      extraTools ? [ ],
      # One derivation with cargo, rustc, clippy and rustfmt. Default: the four from pkgs.
      rustToolchain ? null,
      # The Python interpreter. Default: the one the python module names.
      python ? null,
      # Anything else a language module reads, such as `pythonVenv`.
      options ? { },
    }:
    let
      known = builtins.concatStringsSep ", " (builtins.attrNames self.languages);
      resolve =
        language:
        if builtins.isString language then
          self.languages.${language}
            or (throw "nix-templates/dev: there is no language '${language}'. Known languages: ${known}")
        else if builtins.isPath language then
          import language
        else
          language;
      moduleOptions =
        options // lib.filterAttrs (_: value: value != null) { inherit rustToolchain python; };
      load =
        module:
        if builtins.isFunction module then
          module {
            inherit pkgs lib;
            options = moduleOptions;
          }
        else
          module;

      # The project's languages in the order given, then what every project gets.
      own = map (language: load (resolve language)) languages;
      common = load (import ./languages/common.nix);
      modules = own ++ [ common ];

      wants = flag: lib.any (module: module.${flag} or false) own;
      text = name: list: lib.concatMapStrings (module: module.${name} or "") list;
      # `arch` and `tests` are lists of blocks. Languages that share a build
      # tool share blocks, and a shared block runs once.
      blocks = get: lib.concatStrings (lib.unique (lib.concatMap get own));
      modes = lib.unique (
        [ "run" ] ++ lib.concatMap (module: builtins.attrNames (module.tests or { })) own
      );
      testBlocks = mode: blocks (module: (module.tests or { }).${mode} or [ ]);

      rules = "${arch pkgs}/bin/arch";
      tools = lib.unique (
        lib.concatMap (module: module.tools or [ ]) modules
        ++ lib.optional (wants "semgrep") pkgs.semgrep
        ++ lib.optional (wants "trivy") pkgs.trivy
        ++ extraTools
      );

      usage = lib.concatMapStringsSep ", " (
        mode: if mode == "run" then "tests" else "tests --${mode}"
      ) modes;

      texts = {
        lint = helpers + ''
          ${text "lint" modules}
          exit "$status"
        '';

        # `fmt` writes. `fmt --check` formats a copy and compares, so it covers
        # every formatter, whether or not it has a check mode of its own.
        fmt = helpers + ''
          if [ "''${1:-}" = "--check" ]; then
            keep=(--exclude=/.git --exclude=.direnv --exclude=.venv --exclude=node_modules --exclude=target --exclude=result --exclude=build --exclude=dist --exclude=.build --exclude=_build --exclude=vendor --exclude=.terraform --exclude=.stack-work)
            here=$PWD
            copy=$(mktemp -d)
            trap 'rm -rf "$copy"' EXIT
            rsync -a "''${keep[@]}" ./ "$copy/"
            if [ -e .git ]; then
              ln -s "$here/.git" "$copy/.git"
            fi
            cd "$copy"
          fi

          ${text "fmt" modules}
          if [ "''${1:-}" = "--check" ]; then
            cd "$here"
            changed=$(rsync -rcn --existing "''${keep[@]}" --out-format='%n' "$copy/" ./ | grep -v '/$' || true)
            if [ -n "$changed" ]; then
              echo "fmt would change:"
              while IFS= read -r file; do
                echo "  $file"
              done <<< "$changed"
              status=1
            fi
          fi
          exit "$status"
        '';

        scan = helpers + ''
          ${text "scan" own}
          ${lib.optionalString (wants "semgrep") "run semgrep scan --config auto --error --quiet ."}
          ${lib.optionalString (wants "trivy") "run trivy fs --scanners vuln,secret --no-progress --skip-dirs .direnv --skip-dirs .venv ."}
          ${common.scan}
          exit "$status"
        '';

        # `arch --check` is the rules of architecture.toml, then each language's
        # own architecture tools where the project has their config. Everything
        # else, and machine-readable output, is the rules program alone.
        arch = helpers + ''
          check=
          for argument in "$@"; do
            case "$argument" in
              --check) check=1 ;;
              json | --format=json) exec ${rules} "$@" ;;
            esac
          done
          if [ -z "$check" ]; then
            exec ${rules} "$@"
          fi

          echo ":: arch $*"
          ${rules} "$@" || status=1
          ${blocks (module: module.arch or [ ])}
          exit "$status"
        '';

        # `tests` runs the project's tests. The other modes are there when one
        # of the project's languages has a tool for them.
        tests = helpers + ''
          mode="''${1:-run}"
          mode="''${mode#--}"
          case "$mode" in
          ${lib.concatMapStrings (mode: ''
            ${mode})
              echo ":: tests: ${mode}"
            ${testBlocks mode}
              ;;
          '') modes}
            help | h)
              echo "usage: ${usage}"
              exit 0
              ;;
            *)
              echo "tests: there is no '$mode' here. usage: ${usage}" >&2
              exit 2
              ;;
          esac
          exit "$status"
        '';
      };

      mkScript =
        name: text:
        pkgs.writeShellApplication {
          inherit name text;
          runtimeInputs = tools ++ [
            pkgs.git
            pkgs.rsync
          ];
          # `helpers` is a shared library, so each script legitimately leaves
          # some of its functions unused.
          excludeShellChecks = [ "SC2329" ];
        };

      commands = lib.mapAttrs mkScript texts;

      packages = tools ++ builtins.attrValues commands;
      env = lib.foldl' (acc: module: acc // (module.env or { })) { } modules;
      shellHook = text "shellHook" modules;
      shellAttrs = lib.foldl' (acc: module: acc // (module.shell or { })) { } modules;
      mkShell =
        if lib.any (module: module.needsCC or false) modules then pkgs.mkShell else pkgs.mkShellNoCC;
    in
    {
      # `lint`, `fmt`, `scan`, `arch` and `tests`, each a package.
      inherit commands;

      # The tools alone, and the tools with the commands: for a shell of your own.
      inherit tools packages env;

      # The scripts' text, for checking them without building every tool.
      inherit texts;

      # The modes `tests` has in this project.
      testModes = modes;

      # A ready-made shell with all of it.
      devShell = mkShell (
        shellAttrs
        // {
          inherit packages env;
        }
        // lib.optionalAttrs (shellHook != "") { inherit shellHook; }
      );

      # What can be checked inside the Nix sandbox, without a network.
      checks = lib.optionalAttrs (src != null) {
        # Naming the file makes a missing architecture.toml a failure. A flake
        # only sees files git knows about, so a new one must be `git add`ed.
        arch = pkgs.runCommand "arch-check" { } ''
          ${rules} --check --root ${src} --config ${src}/architecture.toml
          touch $out
        '';
      };
    };

  # Every language as plain data: what it brings and what its commands run.
  # The MCP server answers from this, and the README's tables are made from it.
  catalogue =
    pkgs:
    lib.mapAttrs (
      name: module:
      let
        loaded =
          if builtins.isFunction module then
            module {
              inherit pkgs lib;
              options = { };
            }
          else
            module;
      in
      {
        description = loaded.description or name;
        tools = map (tool: {
          name = tool.pname or (builtins.parseDrvName tool.name).name;
          description = tool.meta.description or "";
        }) (loaded.tools or [ ]);
        lint = loaded.lint or "";
        fmt = loaded.fmt or "";
        scan = loaded.scan or "";
        arch = loaded.arch or [ ];
        tests = loaded.tests or { };
        semgrep = loaded.semgrep or false;
        trivy = loaded.trivy or false;
        nixpkgsConfig = loaded.nixpkgsConfig or [ ];
      }
    ) self.languages;

  self = {
    inherit
      languages
      arch
      mkProject
      catalogue
      ;
  };
in
self
