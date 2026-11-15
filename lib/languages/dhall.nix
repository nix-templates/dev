# Dhall.
{ pkgs, ... }:
{
  description = "Dhall development environment: dhall-lsp-server plus the JSON/Bash/Nix backends";

  tools = with pkgs; [
    # Toolchain: the interpreter formats and lints on its own
    dhall
    dhall-json
    dhall-bash
    dhall-docs
    haskellPackages.dhall-nix

    # Language server
    dhall-lsp-server

  ];

  trivy = true;

  lint = ''
    for_each '*.dhall' dhall lint --check --file
    for_each '*.dhall' dhall format --check --file
  '';

  fmt = ''
    for_each '*.dhall' dhall format --file
  '';
}
