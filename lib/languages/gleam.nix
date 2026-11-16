# Gleam.
{ pkgs, ... }:
{
  description = "Gleam development environment; the gleam binary provides the LSP and formatter";

  tools = with pkgs; [
    # Toolchain: Gleam bundles its own LSP, formatter and build tool
    gleam
    erlang
    rebar3
    nodejs

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when gleam.toml gleam check
    when gleam.toml gleam format --check .
  '';

  style = ''
    when gleam.toml gleam format
  '';

  tests = {
    run = [
      ''
        when gleam.toml gleam test
      ''
    ];
  };
}
