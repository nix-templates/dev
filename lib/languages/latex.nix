# LaTeX.
{ pkgs, ... }:
{
  description = "LaTeX environment: TexLab, ChkTeX, latexindent and Tectonic";

  tools = with pkgs; [
    # Full TeX Live distribution plus the modern Tectonic engine
    texlive.combined.scheme-full
    tectonic

    # Language server
    texlab

    # Prose linting
    vale

    # Rendering helpers
    pandoc

  ];

  quality = ''
    run_on '*.tex' chktex -q
    when .vale.ini vale .
  '';

  style = ''
    run_on '*.tex' latexindent --overwrite --silent
  '';
}
