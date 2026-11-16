# Racket.
{ pkgs, ... }:
{
  description = "Racket development environment; raco fmt and raco test come with the distribution";

  tools = with pkgs; [
    # Toolchain: DrRacket, raco and the full distribution
    racket

  ];

  trivy = true;

  quality = ''
    run_on '*.rkt' raco make -v
  '';

  style = ''
    run typos --write-changes .
  '';

  tests = {
    run = [
      ''
        when_any '*.rkt' raco test .
      ''
    ];
  };
}
