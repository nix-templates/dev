# The library behind the templates.
#
# A project takes this repository as a flake input and calls `mkProject` with
# its own pkgs and the languages it is written in. The tools and the commands
# `quality`, `style`, `security`, `architecture` and `tests` then come from the
# one definition here, so `nix flake update` brings every improvement to every
# project.
#
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

  frameworks = import ./frameworks { inherit lib; };

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

  mkProject =
    {
      # The project's own package set, so tools match what the project builds with.
      pkgs,
      # Optional package set dedicated to tooling, independent of application packages.
      toolPkgs ? pkgs,
      # Names from `languages`, paths to modules of your own, or the modules themselves.
      languages ? [ ],
      # Framework profiles add their languages and refine their commands.
      frameworks ? [ ],
      # Explicit argv from existing project configuration, by canonical category.
      configured ? { },
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
      resolveFramework =
        profile:
        if builtins.isPath profile then
          import profile
        else if builtins.isAttrs profile && ((profile ? module) || !(profile ? name)) then
          profile
        else
          let
            name = if builtins.isString profile then profile else profile.name;
            metadata =
              self.frameworks.${name}
                or (throw "nix-templates/dev: unknown framework '${name}'. Known frameworks: ${lib.concatStringsSep ", " (builtins.attrNames self.frameworks)}");
            version =
              if builtins.isString profile then
                metadata.defaultVersion
              else
                profile.version or metadata.defaultVersion;
          in
          assert lib.assertMsg (lib.elem version metadata.versions)
            "nix-templates/dev: unsupported ${name} version '${version}'. Supported: ${lib.concatStringsSep ", " metadata.versions}";
          metadata
          // {
            inherit name version;
            toolPkgs = if builtins.isAttrs profile then profile.toolPkgs or toolPkgs else toolPkgs;
          };
      profiles = map resolveFramework frameworks;
      frameworkLanguages = lib.concatMap (profile: profile.languages or [ ]) profiles;
      selectedLanguages = lib.unique (languages ++ frameworkLanguages);
      # Defaults do not depend on options: resolve them once, then load profiles
      # with the final project options. Explicit project options win.
      profileDefaults = lib.foldl' (
        acc: profile:
        lib.recursiveUpdate acc ((loadWith options (profile.module or profile)).defaults or { })
      ) { } profiles;
      moduleOptions =
        (lib.recursiveUpdate (
          profileDefaults
          // lib.optionalAttrs (lib.any (spec: spec.runner == "python") (
            lib.concatLists (builtins.attrValues configured)
          )) { pythonProjectEnvironment = true; }
        ) options)
        // lib.filterAttrs (_: value: value != null) { inherit rustToolchain python; };
      loadWithPkgs =
        packageSet: opts: module:
        if builtins.isFunction module then
          module {
            pkgs = packageSet;
            inherit lib;
            options = opts;
          }
        else
          module;
      loadWith = loadWithPkgs toolPkgs;
      load = loadWith moduleOptions;
      frameworkModules = map (
        profile:
        loadWithPkgs (profile.toolPkgs or toolPkgs) (
          moduleOptions
          // {
            frameworkVersion = profile.version or null;
          }
        ) (profile.module or profile)
      ) profiles;
      replacements =
        name: lib.unique (lib.concatMap (module: (module.replace or { }).${name} or [ ]) frameworkModules);
      # A profile can replace a language's command without running both test
      # runners or both formatters. Other language commands are inherited.
      languageModules = lib.zipListsWith (
        language: module: builtins.removeAttrs module (replacements (nameOf language))
      ) selectedLanguages (map (language: load (resolve language)) selectedLanguages);
      configuredModule = import ./configured.nix {
        pkgs = toolPkgs;
        inherit lib configured;
        options = moduleOptions;
      };
      configuredNames = builtins.attrNames configured;
      own =
        (map (module: builtins.removeAttrs module configuredNames) (languageModules ++ frameworkModules))
        ++ lib.optional (configured != { }) configuredModule;
      common = builtins.removeAttrs (load (import ./languages/common.nix)) configuredNames;
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
      named = lib.zipListsWith (name: module: { inherit name module; }) (
        (map nameOf selectedLanguages)
        ++ (map (profile: profile.name or "custom framework") profiles)
        ++ lib.optional (configured != { }) "configured project tools"
      ) own;

      wants = flag: !(configured ? security) && lib.any (module: module.${flag} or false) own;
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
      # A module's `architecture` and `tests` are lists of blocks. Languages that share a build
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

      rules = "${architecture toolPkgs}/bin/architecture";
      tools = lib.unique (
        lib.concatMap (module: module.tools or [ ]) modules
        ++ lib.optional (wants "semgrep") toolPkgs.semgrep
        ++ lib.optional (wants "trivy") toolPkgs.trivy
        ++ extraTools
      );

      usage = lib.concatMapStringsSep ", " (
        mode: if mode == "run" then "tests" else "tests --${mode}"
      ) modes;

      runtimeChecks = lib.concatMapStrings (
        profile:
        lib.optionalString (profile ? distribution) ''
          env -u PYTHONPATH -u PYTHONHOME PYTHONNOUSERSITE=1 "$interpreter" -c ${lib.escapeShellArg ''
            import importlib.metadata, sys
            try:
                actual = importlib.metadata.version(${builtins.toJSON profile.distribution})
            except importlib.metadata.PackageNotFoundError:
                sys.exit("${profile.name}: install the project's existing dependencies first")
            if actual.split(".")[:${toString (builtins.length (lib.splitString "." profile.version))}] != ${builtins.toJSON (lib.splitString "." profile.version)}:
                sys.exit("${profile.name}: profile ${profile.version} does not match installed " + actual + "; select the matching framework version")
          ''} || return $?
        ''
      ) profiles;
      commandHelpers =
        helpers
        + lib.optionalString (moduleOptions.pythonProjectEnvironment or false) (''
          project_python() {
            local interpreter=${lib.escapeShellArg (moduleOptions.projectPython or ".venv/bin/python")}
            interpreter="''${DVT_PROJECT_PYTHON:-$interpreter}"
            if [ ! -x "$interpreter" ]; then
              echo "project Python is missing: $interpreter. Install project dependencies with your existing manager, or set DVT_PROJECT_PYTHON." >&2
              return 127
            fi
            ${runtimeChecks}
            # Nix Python packages must not leak into the application interpreter.
            env -u PYTHONPATH -u PYTHONHOME PYTHONNOUSERSITE=1 "$interpreter" "$@"
          }
        '');

      preflight = lib.concatMapStrings (module: module.preflight or "") (
        frameworkModules ++ lib.optional (configured != { }) configuredModule
      );
      texts = {
        quality =
          commandHelpers
          + preflight
          + ''
            ${parts "quality"}
            ${common.quality or ""}
            checked quality
            exit "$status"
          '';

        # `style` writes. `style --check` formats a copy and compares, so it
        # covers every formatter, whether or not it has a check mode of its own.
        style =
          commandHelpers
          + preflight
          + ''
            if [ "''${1:-}" = "--check" ]; then
              keep=(--exclude=/.git --exclude=.direnv --exclude=.venv --exclude=.bundle --exclude=node_modules --exclude=target --exclude=result --exclude=build --exclude=dist --exclude=.build --exclude=_build --exclude=vendor --exclude=.terraform --exclude=.stack-work)
              here=$PWD
              copy=$(mktemp -d)
              trap 'rm -rf "$copy"' EXIT
              rsync -a "''${keep[@]}" ./ "$copy/"
              # Formatters may load project plugins. Link dependency directories,
              # which remain excluded from the source comparison and formatting.
              for dependency in .venv node_modules vendor .bundle; do
                if [ -d "$here/$dependency" ]; then ln -s "$here/$dependency" "$copy/$dependency"; fi
              done
              if [ ! -e "$copy/node_modules" ] && [ -n "''${DVT_PROJECT_ROOT:-}" ]; then
                if directory=$(cd "$DVT_PROJECT_ROOT" && ${
                  toolPkgs.python3.withPackages (ps: [ ps.pyyaml ])
                }/bin/python3 -I -B ${./frameworks/version_guard.py} --node-modules 2>/dev/null); then
                  ln -s "$directory" "$copy/node_modules"
                fi
              fi
              if [ -e .git ]; then
                ln -s "$here/.git" "$copy/.git"
              fi
              cd "$copy"
            fi

            ${parts "style"}
            ${text "style" [ common ]}
            checked style
            if [ "''${1:-}" = "--check" ]; then
              cd "$here"
              changed=$(rsync -rcn --delete "''${keep[@]}" --out-format='%n' "$copy/" ./ | grep -v '/$' || true)
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
          + commandHelpers
          + preflight
          + ''
            ${parts "security"}
            ${lib.optionalString (wants "semgrep") "run semgrep scan --config auto --error --quiet ."}
            ${lib.optionalString (wants "trivy") "run trivy fs --scanners vuln,secret --no-progress --exit-code 1 --skip-dirs .direnv --skip-dirs .venv ."}
            ${common.security or ""}
            checked security
            exit "$status"
          '';

        # Existing architecture tools are independent of the optional built-in
        # rules file. Explicit rule-engine modes still target that engine.
        architecture =
          commandHelpers
          + preflight
          + ''
            for argument in "$@"; do
              case "$argument" in
                --accept | --prune | --explain | --languages | --version | --help | -h | json | --format=json)
                  exec ${rules} "$@"
                  ;;
              esac
            done

            echo ":: architecture''${*:+ $*}"
            if [ -f architecture.toml ] || [ "$#" -gt 0 ]; then
              run ${rules} "$@"
            fi
            ${blocks (module: module.architecture or [ ])}
            if [ "$status" -ne 0 ]; then
              echo "architecture: FAIL: an architecture tool above did not pass"
            fi
            if [ "$ran" -eq 0 ]; then
              echo "architecture: no configured architecture check was found" >&2
              exit 2
            fi
            exit "$status"
          '';

        # `tests` runs the project's tests. The other modes are there when one
        # of the project's languages has a tool for them.
        tests =
          commandHelpers
          + preflight
          + ''
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
          inherit name;
          text =
            lib.concatStrings (
              lib.mapAttrsToList (key: value: "export ${key}=${lib.escapeShellArg (toString value)}\n") env
            )
            + text;
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
    assert lib.assertMsg (lib.all
      (
        language:
        lib.all
          (
            command:
            builtins.length (
              lib.filter (
                module: lib.elem command ((module.replace or { }).${nameOf language} or [ ])
              ) frameworkModules
            ) <= 1
          )
          [
            "quality"
            "style"
            "security"
            "architecture"
            "tests"
          ]
      )
      selectedLanguages
    ) "Framework profiles replace the same language command; use a custom combined profile instead.";
    {
      # `quality`, `style`, `security`, `architecture` and `tests`, each a package.
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
      checks = lib.optionalAttrs (src != null && builtins.pathExists (src + "/architecture.toml")) {
        # Only the optional source rules can run without project dependencies
        # in the Nix sandbox. Configured project tools run through architecture.
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
        quality = loaded.quality or "";
        style = loaded.style or "";
        security = loaded.security or "";
        architecture = loaded.architecture or [ ];
        tests = loaded.tests or { };
        semgrep = loaded.semgrep or false;
        trivy = loaded.trivy or false;
        nixpkgsConfig = loaded.nixpkgsConfig or [ ];
      }
    ) self.languages;

  self = {
    mkWorkspace = import ./workspace.nix { inherit lib mkProject; };
    inherit
      languages
      frameworks
      architecture
      mkProject
      catalogue
      marks
      ci
      ;
  };
in
self
