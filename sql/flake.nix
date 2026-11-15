{
  description = "A Nix-flake-based SQL environment: sqls language server, SQLFluff, sqruff and pg_format";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1"; # unstable Nixpkgs

    # The tools and checks of this environment are kept in one place, for every
    # project that uses them: lib/languages/sql.nix in nix-templates/dev.
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

      # What this project is written in. Add a name to get that language's tools
      # in the same shell, and its checks in `lint`, `fmt`, `scan`, `arch` and
      # `tests`. The names are the templates of nix-templates/dev.
      project =
        pkgs:
        inputs.dev.lib.mkProject {
          inherit pkgs;
          languages = [ "sql" ];
        };
    in
    {
      devShells = forEachSupportedSystem (
        { pkgs, ... }:
        {
          default = (project pkgs).devShell;
        }
      );

      formatter = forEachSupportedSystem ({ pkgs, ... }: pkgs.nixfmt);
    };
}
