{
  description = "Nix flake templates for development environments that come with linters, formatters, language servers and security scanners";

  inputs.nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1"; # unstable Nixpkgs

  outputs =
    { self, ... }@inputs:
    let
      inherit (inputs.nixpkgs) lib;

      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      forEachSupportedSystem =
        f:
        lib.genAttrs supportedSystems (
          system:
          f {
            inherit system;
            pkgs = import inputs.nixpkgs { inherit system; };
          }
        );
    in
    {
      # The shell used to work *on* this repository, not the one templates give you.
      devShells = forEachSupportedSystem (
        { pkgs, system }:
        {
          default =
            let
              forEachTemplate = exec: ''
                for dir in */; do
                  # lib/ holds the library, not a template.
                  [ -f "''${dir}flake.nix" ] || continue
                  (
                    cd "''${dir}"

                    # A template that takes this repository as an input is checked
                    # against this checkout, not against what is published.
                    override=()
                    if grep -q 'github:nix-templates/dev' flake.nix; then
                      override=(--override-input dev "path:$(dirname "$PWD")")
                    fi

                    ${exec}
                  )
                done
              '';

              script =
                name: runtimeInputs: text:
                pkgs.writeShellApplication {
                  inherit name runtimeInputs text;
                };
            in
            pkgs.mkShellNoCC {
              packages = [
                # Build every template's devShell, to prove they all still resolve.
                (script "build" [ pkgs.nix ] (forEachTemplate ''
                  echo "building ''${dir}"
                  SYSTEM=$(nix eval --impure --raw --expr 'builtins.currentSystem')
                  nix build --no-link "''${override[@]}" ".#devShells.''${SYSTEM}.default"
                ''))

                # Evaluate every template without building anything.
                (script "check" [ pkgs.nix ] (forEachTemplate ''
                  echo "checking ''${dir}"
                  nix flake check --all-systems --no-build "''${override[@]}"
                ''))

                (script "format" [ pkgs.nixfmt ] ''
                  find . -name '*.nix' -not -path './.git/*' -print0 | xargs -0 nixfmt
                '')

                (script "check-formatting" [ pkgs.nixfmt ] ''
                  find . -name '*.nix' -not -path './.git/*' -print0 | xargs -0 nixfmt --check
                '')

                self.formatter.${system}
              ];
            };
        }
      );

      # The library behind the templates: `mkProject` gives a project the tools and
      # checks of the languages it names. See lib/default.nix.
      lib = import ./lib { inherit lib; };

      checks = forEachSupportedSystem (
        { pkgs, system }:
        let
          everything = self.lib.mkProject {
            inherit pkgs;
            languages = builtins.attrNames self.lib.languages;
          };
        in
        {
          # The tests of `layers`.
          layers =
            pkgs.runCommand "layers-tests"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  pkgs.git
                ];
              }
              ''
                cd ${./lib/layers}
                export HOME="$TMPDIR"
                PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m unittest discover -s tests
                touch $out
              '';

          # The MCP server's tests, then the built server asked over stdin for
          # every language the library has.
          mcp =
            pkgs.runCommand "mcp-tests"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  self.packages.${system}.mcp
                ];
              }
              ''
                cd ${./mcp}
                PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:${./lib/layers} python3 -m unittest test_server
                printf '%s\n' \
                  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}' \
                  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
                  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_languages","arguments":{}}}' \
                  | nix-templates-dev-mcp > "$TMPDIR/replies"
                python3 -c '
                import json, sys
                first, second = [json.loads(line) for line in open(sys.argv[1])]
                assert first["result"]["serverInfo"]["name"] == "nix-templates-dev", first
                names = [entry["name"] for entry in json.loads(second["result"]["content"][0]["text"])["languages"]]
                assert names == sorted(sys.argv[2].split()), names
                print(len(names), "languages over MCP")
                ' "$TMPDIR/replies" "${toString (builtins.attrNames self.lib.languages)}"
                touch $out
              '';

          # The tests of `ci`. They find every language of the library in a
          # sample checkout, so they get the marks of all of them.
          ci =
            pkgs.runCommand "ci-tests"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  pkgs.git
                ];
              }
              ''
                mkdir source
                cp -r ${./lib} source/lib
                cp -r ${./mcp} source/mcp
                cd source/lib/ci
                export HOME="$TMPDIR"
                export DEV_CI_MARKS=${pkgs.writeText "marks.json" (builtins.toJSON (self.lib.marks pkgs))}
                PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:../layers:../../mcp python3 -m unittest discover -s tests
                touch $out
              '';

          # The built `ci` on a small checkout, with the commands `mkProject`
          # writes for two languages made for this test. Only nix is a stand-in:
          # a build cannot ask Nix for a dev shell.
          ci-run =
            let
              example = self.lib.mkProject {
                inherit pkgs;
                languages = [
                  ./lib/ci/tests/languages/tested.nix
                  ./lib/ci/tests/languages/untested.nix
                ];
              };
            in
            pkgs.runCommand "ci-run"
              {
                nativeBuildInputs = [
                  self.packages.${system}.ci
                  pkgs.git
                ];
              }
              ''
                export HOME="$TMPDIR"
                export CI_TEST_PATH=${lib.makeBinPath example.packages}
                bash ${./lib/ci/tests/run.sh}
                touch $out
              '';

          # trivy exits 0 on a finding unless it is told --exit-code 1, and it
          # stops on a flag it does not know. Either way `scan` would say nothing
          # about the code. Every trivy line of every language is held to both,
          # by asking trivy itself for help with exactly those flags.
          scan-fails =
            pkgs.runCommand "scan-fails"
              {
                nativeBuildInputs = [ pkgs.trivy ];
                scan = everything.texts.scan;
                passAsFile = [ "scan" ];
              }
              ''
                export HOME="$TMPDIR"
                grep -E '^[[:space:]]*run trivy ' "$scanPath" | sed -E 's/^[[:space:]]*run //' | sort -u > lines
                test -s lines
                while IFS= read -r line; do
                  case "$line" in
                    *" --exit-code 1 "*) ;;
                    *) echo "never fails scan: $line"; exit 1 ;;
                  esac
                  if ! $line --help > /dev/null 2>&1; then
                    echo "trivy does not take these flags: $line"
                    exit 1
                  fi
                done < lines
                echo "$(wc -l < lines) trivy lines fail on a finding"
                touch $out
              '';

          # A Rust project's shell has a C compiler: without `cc`, cargo cannot
          # link a build script, so clippy and the tests stop at the first one.
          # This is evaluated, nothing of Rust is built.
          rust-links =
            assert lib.assertMsg
              (self.lib.mkProject {
                inherit pkgs;
                languages = [ "rust" ];
              }).devShell.stdenv.hasCC
              "the dev shell of a Rust project has no C compiler";
            pkgs.runCommand "rust-links" { } "touch $out";

          # The commands of a project with every language in it pass shellcheck.
          # Building them without their tools keeps this quick.
          scripts = pkgs.linkFarmFromDrvs "library-scripts" (
            lib.mapAttrsToList (
              name: text:
              pkgs.writeShellApplication {
                inherit name text;
                excludeShellChecks = [ "SC2329" ];
              }
            ) everything.texts
          );
        }
      );

      formatter = forEachSupportedSystem ({ pkgs, ... }: pkgs.nixfmt);

      packages = forEachSupportedSystem (
        { pkgs, system }:
        {
          default = self.packages.${system}.dvt;

          # Dependency and purity rules from a repository's architecture.toml.
          layers = self.lib.layers pkgs;

          # What a CI job calls: one of the five commands on a checkout, with or
          # without a flake of its own. `nix run .#ci -- lint`
          ci = self.lib.ci {
            inherit pkgs;
            toolbox = self;
            nixpkgs = inputs.nixpkgs;
            # A checkout with changes in it has no `rev`. Then what Nix calls it,
            # or the hash of the source, stands in.
            revision = self.rev or self.dirtyRev or self.narHash or "an unknown revision";
            nixpkgsRevision = inputs.nixpkgs.rev or lib.version;
          };

          # An MCP server: lets an agent see what the library has and write the
          # flake for a project that uses it. `nix run .#mcp`
          mcp = pkgs.writeShellApplication {
            name = "nix-templates-dev-mcp";
            runtimeInputs = [ pkgs.python3 ];
            text = ''
              export DEV_CATALOGUE=${pkgs.writeText "catalogue.json" (builtins.toJSON (self.lib.catalogue pkgs))}
              PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=${./mcp}:${./lib/layers} exec python3 ${./mcp}/server.py
            '';
          };

          # dvt <template> initialises a template in the current directory.
          dvt = pkgs.writeShellApplication {
            name = "dvt";
            text = ''
              if [ -z "''${1:-}" ]; then
                echo "usage: dvt <template>"
                exit 1
              fi

              nix \
                --experimental-features 'nix-command flakes' \
                flake init \
                --template \
                "github:nix-templates/dev#''${1}"
            '';
          };
        }
      );

      templates = {
        default = self.templates.empty;

        ansible = {
          path = ./ansible;
          description = "Ansible development environment with linters, formatters, LSP and security scanning";
        };

        assembly = {
          path = ./assembly;
          description = "Assembly development environment with linters, formatters, LSP and security scanning";
        };

        bun = {
          path = ./bun;
          description = "Bun development environment with linters, formatters, LSP and security scanning";
        };

        "c-cpp" = {
          path = ./c-cpp;
          description = "C/C++ development environment with linters, formatters, LSP and security scanning";
        };

        clojure = {
          path = ./clojure;
          description = "Clojure development environment with linters, formatters, LSP and security scanning";
        };

        crystal = {
          path = ./crystal;
          description = "Crystal development environment with linters, formatters, LSP and security scanning";
        };

        csharp = {
          path = ./csharp;
          description = "C# development environment with linters, formatters, LSP and security scanning";
        };

        cue = {
          path = ./cue;
          description = "CUE development environment with linters, formatters, LSP and security scanning";
        };

        dart = {
          path = ./dart;
          description = "Dart / Flutter development environment with linters, formatters, LSP and security scanning";
        };

        deno = {
          path = ./deno;
          description = "Deno development environment with linters, formatters, LSP and security scanning";
        };

        dhall = {
          path = ./dhall;
          description = "Dhall development environment with linters, formatters, LSP and security scanning";
        };

        docker = {
          path = ./docker;
          description = "Docker / containers development environment with linters, formatters, LSP and security scanning";
        };

        elixir = {
          path = ./elixir;
          description = "Elixir development environment with linters, formatters, LSP and security scanning";
        };

        elm = {
          path = ./elm;
          description = "Elm development environment with linters, formatters, LSP and security scanning";
        };

        empty = {
          path = ./empty;
          description = "Empty development environment with linters, formatters, LSP and security scanning";
        };

        erlang = {
          path = ./erlang;
          description = "Erlang development environment with linters, formatters, LSP and security scanning";
        };

        fortran = {
          path = ./fortran;
          description = "Fortran development environment with linters, formatters, LSP and security scanning";
        };

        fsharp = {
          path = ./fsharp;
          description = "F# development environment with linters, formatters, LSP and security scanning";
        };

        "github-actions" = {
          path = ./github-actions;
          description = "GitHub Actions development environment with linters, formatters, LSP and security scanning";
        };

        gleam = {
          path = ./gleam;
          description = "Gleam development environment with linters, formatters, LSP and security scanning";
        };

        go = {
          path = ./go;
          description = "Go development environment with linters, formatters, LSP and security scanning";
        };

        graphql = {
          path = ./graphql;
          description = "GraphQL development environment with linters, formatters, LSP and security scanning";
        };

        groovy = {
          path = ./groovy;
          description = "Groovy development environment with linters, formatters, LSP and security scanning";
        };

        hashi = {
          path = ./hashi;
          description = "HashiCorp development environment with linters, formatters, LSP and security scanning";
        };

        haskell = {
          path = ./haskell;
          description = "Haskell development environment with linters, formatters, LSP and security scanning";
        };

        haxe = {
          path = ./haxe;
          description = "Haxe development environment with linters, formatters, LSP and security scanning";
        };

        hdl = {
          path = ./hdl;
          description = "HDL (Verilog/VHDL) development environment with linters, formatters, LSP and security scanning";
        };

        java = {
          path = ./java;
          description = "Java development environment with linters, formatters, LSP and security scanning";
        };

        julia = {
          path = ./julia;
          description = "Julia development environment with linters, formatters, LSP and security scanning";
        };

        jupyter = {
          path = ./jupyter;
          description = "Jupyter development environment with linters, formatters, LSP and security scanning";
        };

        kotlin = {
          path = ./kotlin;
          description = "Kotlin development environment with linters, formatters, LSP and security scanning";
        };

        kubernetes = {
          path = ./kubernetes;
          description = "Kubernetes development environment with linters, formatters, LSP and security scanning";
        };

        latex = {
          path = ./latex;
          description = "LaTeX development environment with linters, formatters, LSP and security scanning";
        };

        lean4 = {
          path = ./lean4;
          description = "Lean 4 development environment with linters, formatters, LSP and security scanning";
        };

        lua = {
          path = ./lua;
          description = "Lua development environment with linters, formatters, LSP and security scanning";
        };

        markdown = {
          path = ./markdown;
          description = "Markdown / docs development environment with linters, formatters, LSP and security scanning";
        };

        nickel = {
          path = ./nickel;
          description = "Nickel development environment with linters, formatters, LSP and security scanning";
        };

        nim = {
          path = ./nim;
          description = "Nim development environment with linters, formatters, LSP and security scanning";
        };

        nix = {
          path = ./nix;
          description = "Nix development environment with linters, formatters, LSP and security scanning";
        };

        node = {
          path = ./node;
          description = "Node.js development environment with linters, formatters, LSP and security scanning";
        };

        ocaml = {
          path = ./ocaml;
          description = "OCaml development environment with linters, formatters, LSP and security scanning";
        };

        odin = {
          path = ./odin;
          description = "Odin development environment with linters, formatters, LSP and security scanning";
        };

        opa = {
          path = ./opa;
          description = "Open Policy Agent development environment with linters, formatters, LSP and security scanning";
        };

        perl = {
          path = ./perl;
          description = "Perl development environment with linters, formatters, LSP and security scanning";
        };

        php = {
          path = ./php;
          description = "PHP development environment with linters, formatters, LSP and security scanning";
        };

        platformio = {
          path = ./platformio;
          description = "PlatformIO development environment with linters, formatters, LSP and security scanning";
        };

        powershell = {
          path = ./powershell;
          description = "PowerShell development environment with linters, formatters, LSP and security scanning";
        };

        presenterm = {
          path = ./presenterm;
          description = "Presenterm development environment with linters, formatters, LSP and security scanning";
        };

        project = {
          path = ./project;
          description = "A project that takes its tools and checks from this repository as a library: several languages in one shell, and architecture rules";
        };

        protobuf = {
          path = ./protobuf;
          description = "Protocol Buffers development environment with linters, formatters, LSP and security scanning";
        };

        pulumi = {
          path = ./pulumi;
          description = "Pulumi development environment with linters, formatters, LSP and security scanning";
        };

        purescript = {
          path = ./purescript;
          description = "PureScript development environment with linters, formatters, LSP and security scanning";
        };

        python = {
          path = ./python;
          description = "Python development environment with linters, formatters, LSP and security scanning";
        };

        r = {
          path = ./r;
          description = "R development environment with linters, formatters, LSP and security scanning";
        };

        racket = {
          path = ./racket;
          description = "Racket development environment with linters, formatters, LSP and security scanning";
        };

        ruby = {
          path = ./ruby;
          description = "Ruby development environment with linters, formatters, LSP and security scanning";
        };

        rust = {
          path = ./rust;
          description = "Rust development environment with linters, formatters, LSP and security scanning";
        };

        scala = {
          path = ./scala;
          description = "Scala development environment with linters, formatters, LSP and security scanning";
        };

        shell = {
          path = ./shell;
          description = "Shell development environment with linters, formatters, LSP and security scanning";
        };

        solidity = {
          path = ./solidity;
          description = "Solidity development environment with linters, formatters, LSP and security scanning";
        };

        sql = {
          path = ./sql;
          description = "SQL development environment with linters, formatters, LSP and security scanning";
        };

        "swi-prolog" = {
          path = ./swi-prolog;
          description = "SWI-Prolog development environment with linters, formatters, LSP and security scanning";
        };

        swift = {
          path = ./swift;
          description = "Swift development environment with linters, formatters, LSP and security scanning";
        };

        terraform = {
          path = ./terraform;
          description = "Terraform / OpenTofu development environment with linters, formatters, LSP and security scanning";
        };

        typescript = {
          path = ./typescript;
          description = "TypeScript development environment with linters, formatters, LSP and security scanning";
        };

        typst = {
          path = ./typst;
          description = "Typst development environment with linters, formatters, LSP and security scanning";
        };

        vlang = {
          path = ./vlang;
          description = "V development environment with linters, formatters, LSP and security scanning";
        };

        web = {
          path = ./web;
          description = "Web front-end development environment with linters, formatters, LSP and security scanning";
        };

        zig = {
          path = ./zig;
          description = "Zig development environment with linters, formatters, LSP and security scanning";
        };

        # Aliases
        c = self.templates."c-cpp";
        cpp = self.templates."c-cpp";
        docs = self.templates.markdown;
        gha = self.templates."github-actions";
        js = self.templates.node;
        k8s = self.templates.kubernetes;
        md = self.templates.markdown;
        sh = self.templates.shell;
        tf = self.templates.terraform;
        ts = self.templates.typescript;

      };
    };
}
