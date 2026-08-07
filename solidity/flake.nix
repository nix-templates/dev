{
  description = "A Nix-flake-based Solidity environment: solc, Foundry and the Slither static analyser";

  inputs.nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1"; # unstable Nixpkgs

  outputs =
    { self, ... }@inputs:

    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      forEachSupportedSystem =
        f:
        inputs.nixpkgs.lib.genAttrs supportedSystems (
          system:
          f {
            inherit system;
            pkgs = import inputs.nixpkgs {
              inherit system;
            };
          }
        );
    in
    {
      devShells = forEachSupportedSystem (
        { pkgs, system }:
        let
          # Everything this environment puts on your PATH: compilers, language
          # servers, linters, formatters and security scanners. Editors pick all
          # of it up automatically once direnv has loaded the shell.
          tools = with pkgs; [
            # Toolchain: the compiler, version manager and the Foundry suite
            solc
            solc-select
            foundry

            # Node.js, for Hardhat and solhint
            nodejs
            pnpm

            # Security: Slither is the standard Solidity SAST tool
            slither-analyzer
            semgrep
            trivy

            # Repo hygiene, spelling and secret scanning
            gitleaks
            typos
            editorconfig-checker
          ];

          # A tiny shell library shared by the three scripts below. `run` keeps
          # going after a failure so that one pass surfaces every problem, and
          # the `when*` / `*_on` wrappers skip a tool when the project has no
          # matching files.
          helpers = ''
            # Shared helpers. `run` keeps going after a failure so you see every problem in
            # one pass; `run_on` skips a tool entirely when the project has no such files.
            status=0

            run() {
              echo ":: $*"
              "$@" || status=1
            }

            collect() {
              find . \( -name .git -o -name .direnv -o -name .venv -o -name node_modules -o -name target -o -name result -o -name build -o -name dist -o -name .build -o -name _build -o -name vendor -o -name .terraform -o -name .stack-work \) -prune -o -type f -name "$1" -print
            }

            run_on() {
              local pattern="$1"
              shift
              local files=()
              mapfile -t files < <(collect "$pattern")
              if [ "''${#files[@]}" -eq 0 ]; then
                echo ":: skipping $1 (no $pattern files)"
                return
              fi
              run "$@" "''${files[@]}"
            }

            for_each() {
              local pattern="$1"
              shift
              local files=()
              mapfile -t files < <(collect "$pattern")
              if [ "''${#files[@]}" -eq 0 ]; then
                echo ":: skipping $1 (no $pattern files)"
                return
              fi
              local file
              for file in "''${files[@]}"; do
                run "$@" "$file"
              done
            }

            if_have() {
              local bin="$1"
              shift
              if command -v "$bin" > /dev/null 2>&1; then
                run "$@"
              else
                echo ":: skipping $1 ($bin is not on PATH)"
              fi
            }

            when() {
              local guard="$1"
              shift
              if [ -e "$guard" ]; then
                run "$@"
              else
                echo ":: skipping $1 (no $guard here)"
              fi
            }

            when_any() {
              local pattern="$1"
              shift
              if [ -n "$(collect "$pattern" | head -n 1)" ]; then
                run "$@"
              else
                echo ":: skipping $1 (no $pattern files)"
              fi
            }
          '';

          # `lint`, `fmt` and `scan` are the single source of truth for this
          # environment's checks: the terminal, the VS Code tasks in
          # .vscode/tasks.json and Neovim's :DevLint / :DevFmt / :DevScan
          # commands all run exactly these.
          mkScript =
            name: text:
            pkgs.writeShellApplication {
              inherit name;
              text = helpers + text;
              runtimeInputs = tools;
              # `helpers` is a shared library, so each script legitimately leaves
              # some of its functions unused.
              excludeShellChecks = [ "SC2329" ];
            };

          lint = mkScript "lint" ''
            # Run every linter and static analyser for the Solidity environment.

            when foundry.toml forge build --sizes
            if_have solhint solhint 'contracts/**/*.sol'
            run typos --format brief .
            run editorconfig-checker -format gcc -exclude '(^|/)(\.direnv|\.venv|\.git|node_modules|vendor|result|dist|build|target)/'
            exit "$status"
          '';

          fmt = mkScript "fmt" ''
            # Format every file this Solidity environment knows how to format.

            when foundry.toml forge fmt
            exit "$status"
          '';

          scan = mkScript "scan" ''
            # Security scan: SAST, dependency and secret checks for Solidity.

            when foundry.toml slither . --exclude-dependencies
            run semgrep scan --config auto --error --quiet .
            run trivy fs --scanners vuln,secret --no-progress --skip-dirs .direnv --skip-dirs .venv .
            run gitleaks dir . --no-banner --redact
            exit "$status"
          '';
        in
        {
          default = pkgs.mkShellNoCC {
            packages = tools ++ [
              lint
              fmt
              scan
              self.formatter.${system}
            ];

          };
        }
      );

      formatter = forEachSupportedSystem ({ pkgs, ... }: pkgs.nixfmt);
    };
}
