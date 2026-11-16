# V.
{ pkgs, ... }:
{
  description = "V development environment; v vet and v fmt are built into the compiler";

  tools = with pkgs; [
    # Toolchain: v fmt and v vet are built in
    vlang

  ];

  trivy = true;

  quality = ''
    when_any '*.v' v vet .
    when_any '*.v' v fmt -verify .
  '';

  style = ''
    when_any '*.v' v fmt -w .
  '';

  tests = {
    run = [
      ''
        when_any '*_test.v' v test .
      ''
    ];
  };
}
