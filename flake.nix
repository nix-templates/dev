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
                  (
                    cd "''${dir}"

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
                  nix build --no-link ".#devShells.''${SYSTEM}.default"
                ''))

                # Evaluate every template without building anything.
                (script "check" [ pkgs.nix ] (forEachTemplate ''
                  echo "checking ''${dir}"
                  nix flake check --all-systems --no-build
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

      formatter = forEachSupportedSystem ({ pkgs, ... }: pkgs.nixfmt);

      packages = forEachSupportedSystem (
        { pkgs, system }:
        {
          default = self.packages.${system}.dvt;

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
