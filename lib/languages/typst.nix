# Typst.
{ pkgs, ... }:
{
  description = "Typst environment: Tinymist language server and the typstyle formatter";

  tools = with pkgs; [
    # Toolchain
    typst

    # Language server
    tinymist

    # Formatter
    typstyle

    # Prose linting and conversion
    vale
    pandoc

  ];

  lint = ''
    run_on '*.typ' typstyle --check
    when .vale.ini vale .
  '';

  fmt = ''
    run_on '*.typ' typstyle --inplace
  '';
}
