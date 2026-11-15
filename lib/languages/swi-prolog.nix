# SWI-Prolog.
{ pkgs, ... }:
{
  description = "SWI-Prolog development environment";

  tools = with pkgs; [
    # Toolchain
    swi-prolog

  ];

  lint = ''
    for_each '*.pl' swipl -q -g halt -t 'halt(1).'
  '';

  fmt = ''
    run typos --write-changes .
  '';
}
