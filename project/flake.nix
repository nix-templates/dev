{
  description = "A Nix-flake-based project that takes its tools and checks from nix-templates/dev as a library: several languages in one shell, and architecture rules";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1"; # unstable Nixpkgs

    # The tools and checks. `nix flake update dev` brings in newer ones.
    dev.url = "github:nix-templates/dev";
    dev.inputs.nixpkgs.follows = "nixpkgs";
  };

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
            pkgs = import inputs.nixpkgs { inherit system; };
          }
        );

      # Everything this project is written in. Each name adds that language's
      # compilers, language servers, linters, formatters and scanners to the
      # shell, and its checks to `lint`, `fmt`, `scan`, `layers` and `tests`.
      # The names are the templates of nix-templates/dev: rust, python, go, ...
      project =
        pkgs:
        inputs.dev.lib.mkProject {
          inherit pkgs;
          languages = [
            "nix"
            "shell"
          ];
          src = self;
        };
    in
    {
      # `lint`, `fmt`, `scan`, `layers` and `tests` are on PATH in this shell.
      devShells = forEachSupportedSystem (
        { pkgs, ... }:
        {
          default = (project pkgs).devShell;
        }
      );

      # `nix flake check` checks the rules in architecture.toml.
      checks = forEachSupportedSystem ({ pkgs, ... }: (project pkgs).checks);

      formatter = forEachSupportedSystem ({ pkgs, ... }: pkgs.nixfmt);
    };
}
