# PureScript.
{ pkgs, ... }:
{
  description = "PureScript development environment with Spago and the Node toolchain";

  tools = with pkgs; [
    # Toolchain
    purescript
    spago
    nodejs
    esbuild

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when spago.yaml spago build --censor-stats
  '';

  style = ''
    if_have purs-tidy purs-tidy format-in-place src
  '';

  tests = {
    run = [
      ''
        if [ -e spago.yaml ] || [ -e spago.dhall ]; then
          run spago test
        fi
      ''
    ];
  };
}
