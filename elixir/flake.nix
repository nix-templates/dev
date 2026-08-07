{
  description = "A Nix-flake-based Elixir development environment: ElixirLS plus mix format and mix credo";

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
            # Toolchain: Elixir brings OTP, mix, hex and rebar3 with it
            elixir
            git

            # Language server
            elixir-ls

            # Node.js, for Phoenix asset pipelines
            nodejs

            # Security
            semgrep
            trivy

            # Repo hygiene, spelling and secret scanning
            gitleaks
            typos
            editorconfig-checker
          ];

          # Tools that only exist, or only make sense, on one platform.
          platformTools =
            with pkgs;
            lib.optionals stdenv.hostPlatform.isLinux [
              inotify-tools
              libnotify
              gigalixir
            ]
            ++ lib.optionals stdenv.hostPlatform.isDarwin [
              terminal-notifier
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
            # Run every linter and static analyser for the Elixir environment.

            when mix.exs mix compile --warnings-as-errors
            when mix.exs mix format --check-formatted
            run typos --format brief .
            run editorconfig-checker -format gcc -exclude '(^|/)(\.direnv|\.venv|\.git|node_modules|vendor|result|dist|build|target)/'
            exit "$status"
          '';

          fmt = mkScript "fmt" ''
            # Format every file this Elixir environment knows how to format.

            when mix.exs mix format
            exit "$status"
          '';

          scan = mkScript "scan" ''
            # Security scan: SAST, dependency and secret checks for Elixir.

            run semgrep scan --config auto --error --quiet .
            run trivy fs --scanners vuln,secret --no-progress --skip-dirs .direnv --skip-dirs .venv .
            run gitleaks dir . --no-banner --redact
            exit "$status"
          '';
        in
        {
          default = pkgs.mkShellNoCC {
            packages =
              tools
              ++ [
                lint
                fmt
                scan
                self.formatter.${system}
              ]
              ++ platformTools;

          };
        }
      );

      formatter = forEachSupportedSystem ({ pkgs, ... }: pkgs.nixfmt);
    };
}
