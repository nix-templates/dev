# Nix.
{ pkgs, ... }:
{
  description = "Nix development environment: nixd, nixfmt, statix, deadnix and vulnix";

  tools = with pkgs; [
    # Language server
    nixd

    # Linters and dead-code detection
    statix
    deadnix

    # Formatter
    nixfmt

    # Security: scan a system or closure for known vulnerabilities
    vulnix

    # Everyday flake and store tooling
    nix-tree
    nix-diff
    nurl
    nix-init
    cachix
    niv

    # Tests: unit tests and snapshot tests for Nix code
    nix-unit
    namaka
  ];

  trivy = true;

  quality = ''
    run statix check .
    run deadnix --fail .
    run_on '*.nix' nixfmt --check
  '';

  style = ''
    run_on '*.nix' nixfmt
    run statix fix .
  '';

  tests = {
    run = [
      ''
        when tests/default.nix nix-unit tests/default.nix
      ''
      ''
        when namaka.toml namaka check
      ''
    ];
  };
}
