# Odin.
{ pkgs, ... }:
{
  description = "Odin development environment with the ols language server";

  tools = with pkgs; [
    # Toolchain: odin fmt is built in
    odin

    # Language server
    ols

  ];

  trivy = true;

  quality = ''
    when_any '*.odin' odin check .
  '';

  style = ''
    run odin fmt .
  '';

  tests = {
    run = [
      ''
        when_any '*.odin' odin test . -all-packages
      ''
    ];
  };
}
