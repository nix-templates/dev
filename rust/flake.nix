{
  description = "A Nix-flake-based Rust development environment: rust-analyzer, clippy, rustfmt, cargo-audit and cargo-deny";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1"; # unstable Nixpkgs

    fenix = {
      url = "https://flakehub.com/f/nix-community/fenix/0.1";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # The tools and checks of this environment are kept in one place, for every
    # project that uses them: lib/languages/rust.nix in nix-templates/dev.
    # `nix flake update dev` brings in newer ones.
    dev = {
      url = "github:nix-templates/dev";
      inputs.nixpkgs.follows = "nixpkgs";
    };
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

      # A single, pinned toolchain so `cargo`, `clippy` and `rustfmt` can never
      # disagree about the compiler they were built against. `llvm-tools` is
      # what `tests --coverage` (cargo-llvm-cov) reads coverage with.
      toolchain =
        system:
        with inputs.fenix.packages.${system};
        combine (
          with stable;
          [
            cargo
            clippy
            rustc
            rustfmt
            rust-src
            llvm-tools
          ]
        );

      # What this project is written in. Add a name to get that language's tools
      # in the same shell, and its checks in `lint`, `fmt`, `scan`, `layers` and
      # `tests`. The names are the templates of nix-templates/dev.
      project =
        pkgs: system:
        inputs.dev.lib.mkProject {
          inherit pkgs;
          languages = [ "rust" ];
          rustToolchain = toolchain system;
        };
    in
    {
      devShells = forEachSupportedSystem (
        { pkgs, system }:
        {
          default = pkgs.mkShellNoCC {
            inherit (project pkgs system) packages;

            env = (project pkgs system).env // {
              RUST_SRC_PATH = "${toolchain system}/lib/rustlib/src/rust/library";
            };
          };
        }
      );

      formatter = forEachSupportedSystem ({ pkgs, ... }: pkgs.nixfmt);
    };
}
