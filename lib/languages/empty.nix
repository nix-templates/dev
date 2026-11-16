# Starter.
{ pkgs, ... }:
{
  description = "Starter environment with only the language-agnostic linters and scanners";

  # Never found by itself: this is a starting point, not a language.
  marks = [ ];

  tools = with pkgs; [

    # Language-agnostic formatters worth keeping
    treefmt
    dprint
    taplo
    yamlfmt

    # Linters that apply to any repository
    yamllint
    markdownlint-cli2
    actionlint

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    run yamllint --strict .
    run markdownlint-cli2 '**/*.md'
    when .github/workflows actionlint
  '';

  style = ''
    run yamlfmt .
    when taplo.toml taplo fmt
  '';
}
