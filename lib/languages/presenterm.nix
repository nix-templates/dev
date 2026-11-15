# Terminal-slides.
{ pkgs, ... }:
{
  description = "Terminal-slides environment: Presenterm, Mermaid, Typst and markdown linting";

  # Never found by itself: slides are Markdown like any other.
  marks = [ ];

  tools = with pkgs; [
    # Slide rendering
    presenterm
    mermaid-cli
    typst
    pandoc

    # Language servers for the slide markdown
    marksman
    harper

    # Linters
    markdownlint-cli2
    vale

    # Formatter
    prettier

  ];

  lint = ''
    run markdownlint-cli2 '**/*.md'
    when .vale.ini vale .
  '';

  fmt = ''
    run prettier --write --log-level warn '**/*.md'
  '';
}
