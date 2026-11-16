# SWI-Prolog.
{ pkgs, ... }:
{
  description = "SWI-Prolog development environment";

  tools = with pkgs; [
    # Toolchain
    swi-prolog

  ];

  quality = ''
    for_each '*.pl' swipl -q -g halt -t 'halt(1).'
  '';

  style = ''
    run typos --write-changes .
  '';
}
