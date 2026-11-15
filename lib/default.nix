# The library behind the templates.
#
# A project takes this repository as a flake input and calls `mkProject` with
# its own pkgs and the languages it is written in. The tools and the commands
# `quality`, `style`, `security`, `architecture` and `tests` then come from the
# one definition here, so `nix flake update` brings every improvement to every
# project.
#
# The commands were `lint`, `fmt`, `scan` and `layers` before. A language's
# module still names its part of each command that way, and so does the folder
# of the architecture program.
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

  # The program that checks a repository against its architecture.toml.
  architecture =
    pkgs:
    pkgs.writeShellApplication {
      name = "architecture";
      runtimeInputs = [
        pkgs.python3
        pkgs.git
      ];
      text = ''
        PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=${./layers} exec python3 -m layers "$@"
      '';
    };

  # What four of the commands were called before. The old names stay, so that
  # habits, editor tasks and the pipelines of older projects go on working.
  formerly = {
    quality = "lint";
    style = "fmt";
    security = "scan";
    architecture = "layers";
  };

  # A command under its old name: it says what it is called now, and runs it.
  renamed =
    pkgs: before: now: command:
    pkgs.writeShellApplication {
      name = before;
      text = ''
        echo "${before} is called ${now} now" >&2
        exec ${command}/bin/${now} "$@"
      '';
    };

  # The architecture program under its old name.
  layers = pkgs: renamed pkgs "layers" "architecture" (architecture pkgs);

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

      # What a command calls each language when it says what it ran nothing for.
      nameOf =
        language:
        if builtins.isString language then
          language
        else if builtins.isPath language then
          lib.removeSuffix ".nix" (baseNameOf language)
        else
          "a language of your own";
      named = lib.zipListsWith (name: module: { inherit name module; }) (map nameOf languages) own;

      wants = flag: lib.any (module: module.${flag} or false) own;
      text = name: list: lib.concatMapStrings (module: module.${name} or "") list;
      # A command's text for the project's languages: each language's part
      # under its name, then `part_end` for what follows them.
      parts =
        name:
        lib.concatMapStrings (
          entry:
          lib.optionalString ((entry.module.${name} or "") != "") ''
            part ${lib.escapeShellArg entry.name}
            ${entry.module.${name}}
          ''
        ) named
        + ''
          part_end
        '';
      # A module's `layers` and `tests` are lists of blocks. Languages that share a build
      # tool share blocks, and a shared block runs once.
      blocks = get: lib.concatStrings (lib.unique (lib.concatMap get own));
      modes = lib.unique (
        [ "run" ] ++ lib.concatMap (module: builtins.attrNames (module.tests or { })) own
      );
      # The blocks of a test mode, each as the part of the languages that have it.
      testBlocks =
        mode:
        let
          of = module: (module.tests or { }).${mode} or [ ];
        in
        lib.concatMapStrings (block: ''
          part ${
            lib.escapeShellArgs (
              map (entry: entry.name) (lib.filter (entry: lib.elem block (of entry.module)) named)
            )
          }
          ${block}
        '') (lib.unique (lib.concatMap of own));

      rules = "${architecture pkgs}/bin/architecture";
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
        quality = helpers + ''
          ${parts "lint"}
          ${common.lint}
          checked quality
          exit "$status"
        '';

        # `style` writes. `style --check` formats a copy and compares, so it
        # covers every formatter, whether or not it has a check mode of its own.
        style = helpers + ''
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

          ${parts "fmt"}
          ${text "fmt" [ common ]}
          checked style
          if [ "''${1:-}" = "--check" ]; then
            cd "$here"
            changed=$(rsync -rcn --existing "''${keep[@]}" --out-format='%n' "$copy/" ./ | grep -v '/$' || true)
            if [ -n "$changed" ]; then
              echo "style would change:"
              while IFS= read -r file; do
                echo "  $file"
              done <<< "$changed"
              status=1
            fi
          fi
          exit "$status"
        '';

        # trivy reports and exits 0 unless told otherwise, so every trivy line
        # says --exit-code 1: a scanner that cannot fail is no check.
        security =
          # macOS has a `security` of its own, the keychain tool, and programs
          # call it by that name. It never runs without arguments and this
          # command takes none, so with arguments it is the keychain tool.
          lib.optionalString pkgs.stdenv.hostPlatform.isDarwin ''
            if [ "$#" -gt 0 ] && [ -x /usr/bin/security ]; then
              exec /usr/bin/security "$@"
            fi
          ''
          + helpers
          + ''
            ${parts "scan"}
            ${lib.optionalString (wants "semgrep") "run semgrep scan --config auto --error --quiet ."}
            ${lib.optionalString (wants "trivy") "run trivy fs --scanners vuln,secret --no-progress --exit-code 1 --skip-dirs .direnv --skip-dirs .venv ."}
            ${common.scan}
            checked security
            exit "$status"
          '';

        # `architecture` is the rules of architecture.toml, then each language's
        # own architecture tools where the project has their config. Its other
        # modes, and machine-readable output, are the rules program alone.
        architecture = helpers + ''
          for argument in "$@"; do
            case "$argument" in
              --accept | --prune | --explain | --languages | --version | --help | -h | json | --format=json)
                exec ${rules} "$@"
                ;;
            esac
          done

          echo ":: architecture''${*:+ $*}"
          rules=0
          ${rules} "$@" || rules=1
          ${blocks (module: module.layers or [ ])}
          if [ "$status" -ne 0 ]; then
            echo "architecture: FAIL: an architecture tool above did not pass"
          fi
          if [ "$rules" -ne 0 ]; then
            status=1
          fi
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
              checked ${lib.escapeShellArg (if mode == "run" then "tests" else "tests --${mode}")}
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

      now = lib.mapAttrs mkScript texts;
      # The five commands, and four of them under their old names as well.
      commands =
        now
        // lib.mapAttrs' (
          name: before: lib.nameValuePair before (renamed pkgs before name now.${name})
        ) formerly;

      packages = tools ++ builtins.attrValues commands;
      env = lib.foldl' (acc: module: acc // (module.env or { })) { } modules;
      shellHook = text "shellHook" modules;
      shellAttrs = lib.foldl' (acc: module: acc // (module.shell or { })) { } modules;
      mkShell =
        if lib.any (module: module.needsCC or false) modules then pkgs.mkShell else pkgs.mkShellNoCC;
    in
    {
      # `quality`, `style`, `security`, `architecture` and `tests`, each a
      # package, and `lint`, `fmt`, `scan` and `layers`, which run them.
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
        architecture = pkgs.runCommand "architecture-check" { } ''
          ${rules} --check --root ${src} --config ${src}/architecture.toml
          touch $out
        '';
      };
    };

  # A language's module as it is without options of the project.
  plain =
    pkgs: module:
    if builtins.isFunction module then
      module {
        inherit pkgs lib;
        options = { };
      }
    else
      module;

  # How each language is told from the files of a checkout. `marks` are file
  # names or globs; a language without them is found by the files `architecture`
  # reads as that language. `insteadOf` names the languages it then stands in
  # for. `ci` reads this for a checkout that names no languages itself.
  marks =
    pkgs:
    lib.mapAttrs (
      _: module:
      let
        loaded = plain pkgs module;
      in
      {
        marks = loaded.marks or null;
        insteadOf = loaded.insteadOf or [ ];
      }
    ) self.languages;

  # The program a CI job calls: one of the five commands on a checkout, in the
  # checkout's own dev shell or in one made for the languages found in it.
  # See lib/ci.
  ci =
    {
      pkgs,
      # This repository and the nixpkgs it runs with, as source trees. The dev
      # shell of a checkout without a flake is made from these two.
      toolbox,
      nixpkgs,
      # What to call them in the first line of a run.
      revision ? "an unknown revision",
      nixpkgsRevision ? lib.version,
    }:
    let
      settings = pkgs.writeText "ci-settings.json" (
        builtins.toJSON {
          toolbox = "${toolbox}";
          nixpkgs = "${nixpkgs}";
          inherit (pkgs.stdenv.hostPlatform) system;
          inherit revision nixpkgsRevision;
          bash = "${pkgs.bash}/bin/bash";
          env = "${pkgs.coreutils}/bin/env";
          marks = marks pkgs;
        }
      );
      # Nothing of ci's own may reach the command it runs, so the paths are
      # given to Python here and not through the environment.
      start = pkgs.writeText "ci.py" ''
        import sys

        sys.path[:0] = ["${./ci}", "${./layers}", "${../mcp}"]

        from ci.cli import main

        sys.exit(main(settings="${settings}"))
      '';
    in
    pkgs.writeShellApplication {
      name = "ci";
      # git is behind PATH, for a machine that has none of its own.
      text = ''
        PATH="$PATH:${pkgs.git}/bin" exec ${pkgs.python3}/bin/python3 -B ${start} "$@"
      '';
    };

  # Every language as plain data: what it brings and what its commands run.
  # The MCP server answers from this, and the README's tables are made from it.
  catalogue =
    pkgs:
    lib.mapAttrs (
      name: module:
      let
        loaded = plain pkgs module;
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
        layers = loaded.layers or [ ];
        tests = loaded.tests or { };
        semgrep = loaded.semgrep or false;
        trivy = loaded.trivy or false;
        nixpkgsConfig = loaded.nixpkgsConfig or [ ];
      }
    ) self.languages;

  self = {
    inherit
      languages
      architecture
      layers
      formerly
      mkProject
      catalogue
      marks
      ci
      ;
  };
in
self
