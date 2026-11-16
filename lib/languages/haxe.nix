# Haxe.
{ pkgs, ... }:
{
  description = "Haxe development environment with the Neko VM";

  tools = with pkgs; [
    # Toolchain: the Haxe compiler ships its own language server
    haxe
    neko

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when build.hxml haxe build.hxml
  '';

  style = ''
    run typos --write-changes .
  '';
}
