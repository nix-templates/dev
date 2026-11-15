# Nix.
{ pkgs, ... }:
{
  tools = with pkgs; [
    nixd
    statix
    deadnix
    nixfmt
    vulnix
    nix-tree
    nix-diff
    nurl
    nix-init
    cachix
    niv
  ];

  lint = ''
    run statix check .
    run deadnix --fail .
    run_on '*.nix' nixfmt --check
  '';

  fmt = ''
    run_on '*.nix' nixfmt
    run statix fix .
  '';

  fmtCheck = ''
    run_on '*.nix' nixfmt --check
  '';
}
