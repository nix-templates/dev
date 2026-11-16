# CUE.
{ pkgs, ... }:
{
  description = "CUE development environment with the cuelsp language server";

  tools = with pkgs; [
    # Toolchain: cue vet and cue fmt are built in
    cue

    # Language server
    cuelsp

  ];

  trivy = true;

  quality = ''
    when cue.mod cue vet ./...
    run cue fmt --check ./...
  '';

  style = ''
    run cue fmt ./...
  '';

  tests = {
    run = [
      ''
        when cue.mod cue vet -c=false ./...
      ''
    ];
  };
}
