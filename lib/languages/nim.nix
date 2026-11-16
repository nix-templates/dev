# Nim.
{ pkgs, ... }:
{
  description = "Nim development environment: nimlangserver and the nph formatter";

  tools = with pkgs; [
    # Toolchain
    nim
    nimble

    # Language server
    nimlangserver

    # Formatter
    nph

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    for_each '*.nim' nim check --hints:off
    run_on '*.nim' nph --check
  '';

  style = ''
    run_on '*.nim' nph
  '';

  tests = {
    run = [
      ''
        when_any '*.nimble' nimble test
      ''
    ];
  };
}
