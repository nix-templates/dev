# The library behind the templates.
#
# A project takes this repository as a flake input and calls `mkProject` with
# its own pkgs and the languages it is written in. The tools, `lint`, `fmt`,
# `scan` and `archcheck` then come from the one definition here, so
# `nix flake update` brings every improvement to every project that uses it.
{ lib }:
let
  helpers = builtins.readFile ./helpers.sh;

  languages = {
    "c-cpp" = import ./languages/c-cpp.nix;
    nix = import ./languages/nix.nix;
    python = import ./languages/python.nix;
    qml = import ./languages/qml.nix;
    rust = import ./languages/rust.nix;
    shell = import ./languages/shell.nix;
  };

  # Dependency and purity rules from a repository's architecture.toml.
  archcheck =
    pkgs:
    pkgs.writeShellApplication {
      name = "archcheck";
      runtimeInputs = [
        pkgs.python3
        pkgs.git
      ];
      text = ''
        PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=${./archcheck} exec python3 -m archcheck "$@"
      '';
    };

  mkProject =
    {
      # The project's own package set, so tools match what the project builds with.
      pkgs,
      # Names from `languages`, or modules of the same shape for anything else.
      languages ? [ ],
      # The source tree, for `checks`. In a flake this is `self`.
      src ? null,
      # More packages for the shell and the commands' PATH.
      extraTools ? [ ],
      # One derivation with cargo, rustc, clippy and rustfmt. Default: the four from pkgs.
      rustToolchain ? null,
      # The Python interpreter. Default: pkgs.python3.
      python ? null,
      # Passed on to language modules of your own.
      options ? { },
    }:
    let
      known = builtins.concatStringsSep ", " (builtins.attrNames self.languages);
      resolve =
        language:
        if builtins.isString language then
          self.languages.${language}
            or (throw "nix-templates/dev: there is no language '${language}'. Known languages: ${known}")
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
      modules = own ++ [ (load (import ./languages/common.nix)) ];

      gather = name: lib.concatMapStrings (module: module.${name} or "") modules;
      wantsSemgrep = lib.any (module: module.semgrep or false) modules;

      archcheckCommand = archcheck pkgs;
      tools = lib.unique (
        lib.concatMap (module: module.tools or [ ]) modules
        ++ lib.optional wantsSemgrep pkgs.semgrep
        ++ extraTools
      );

      texts = {
        lint = helpers + ''
          ${gather "lint"}
          when architecture.toml archcheck
          exit "$status"
        '';

        # `fmt` writes; `fmt --check` only reports, for CI.
        fmt = helpers + ''
          if [ "''${1:-}" = "--check" ]; then
            :
          ${gather "fmtCheck"}
          else
            :
          ${gather "fmt"}
          fi
          exit "$status"
        '';

        scan = helpers + ''
          ${lib.concatMapStrings (module: module.scan or "") own}
          ${lib.optionalString wantsSemgrep "run semgrep scan --config auto --error --quiet ."}
          ${(lib.last modules).scan}
          exit "$status"
        '';
      };

      mkScript =
        name: text:
        pkgs.writeShellApplication {
          inherit name text;
          runtimeInputs = tools ++ [ archcheckCommand ];
          # `helpers` is a shared library, so each script legitimately leaves
          # some of its functions unused.
          excludeShellChecks = [ "SC2329" ];
        };

      commands = lib.mapAttrs mkScript texts // {
        archcheck = archcheckCommand;
      };

      packages = tools ++ builtins.attrValues commands;
      env = lib.foldl' (acc: module: acc // (module.env or { })) { } modules;
      needsCC = lib.any (module: module.needsCC or false) modules;
    in
    {
      # `lint`, `fmt`, `scan` and `archcheck`, each a package.
      inherit commands;

      # The tools alone, and the tools with the commands: for a shell of your own.
      inherit tools packages env;

      # The scripts' text, for checking them without building every tool.
      inherit texts;

      # A ready-made shell with all of it.
      devShell = (if needsCC then pkgs.mkShell else pkgs.mkShellNoCC) { inherit packages env; };

      # What can be checked inside the Nix sandbox, without a network.
      checks = lib.optionalAttrs (src != null) {
        # Naming the file makes a missing architecture.toml a failure. A flake
        # only sees files git knows about, so a new one must be `git add`ed.
        archcheck = pkgs.runCommand "archcheck" { nativeBuildInputs = [ archcheckCommand ]; } ''
          archcheck --root ${src} --config ${src}/architecture.toml
          touch $out
        '';
      };
    };

  self = { inherit languages archcheck mkProject; };
in
self
