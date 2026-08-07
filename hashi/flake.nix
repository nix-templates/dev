{
  description = "A Nix-flake-based HashiCorp environment: Terraform, Vault, Nomad, Consul, Packer and their linters";

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
              # Terraform, Vault, Nomad, Consul and Packer moved to the BUSL, which
              # nixpkgs classifies as unfree. Opting in is what makes this shell work.
              config.allowUnfree = true;
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
            # The HashiCorp stack
            terraform
            vault
            nomad
            consul
            packer
            terragrunt
            nomad-autoscaler
            nomad-pack
            levant
            damon

            # Language server
            terraform-ls

            # Linters and documentation
            tflint
            terraform-docs

            # Security: infrastructure-as-code SAST
            tfsec
            checkov
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
            # Run every linter and static analyser for the HashiCorp environment.

            when_any '*.tf' terraform fmt -check -recursive
            when_any '*.tf' tflint --recursive
            when_any '*.pkr.hcl' packer fmt -check -recursive .
            run typos --format brief .
            run editorconfig-checker -format gcc -exclude '(^|/)(\.direnv|\.venv|\.git|node_modules|vendor|result|dist|build|target)/'
            exit "$status"
          '';

          fmt = mkScript "fmt" ''
            # Format every file this HashiCorp environment knows how to format.

            when_any '*.tf' terraform fmt -recursive
            exit "$status"
          '';

          scan = mkScript "scan" ''
            # Security scan: SAST, dependency and secret checks for HashiCorp.

            when_any '*.tf' tfsec --soft-fail=false .
            when_any '*.tf' checkov --quiet --compact --directory .
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
