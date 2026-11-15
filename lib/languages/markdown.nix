# Documentation.
{ pkgs, ... }:
{
  description = "Documentation environment: Marksman, markdownlint, Vale, Harper and lychee";

  # Markdown files.
  marks = [
    "*.md"
  ];

  tools = with pkgs; [
    # Language servers: Marksman for structure, Harper for prose
    marksman
    harper

    # Linters: markdownlint for style, Vale for prose, lychee for dead links
    markdownlint-cli2
    vale
    lychee

    # Formatters
    mdformat
    prettier

    # Rendering and diagrams
    pandoc
    mdbook
    mermaid-cli

  ];

  lint = ''
    run markdownlint-cli2 '**/*.md'
    when .vale.ini vale .
  '';

  fmt = ''
    run prettier --write --log-level warn '**/*.md'
  '';

  scan = ''
    run lychee --no-progress --offline --exclude-path .direnv .
  '';
}
