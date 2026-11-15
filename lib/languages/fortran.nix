# Fortran.
{ pkgs, ... }:
{
  description = "Fortran development environment: fortls, fprettify and the Fortran package manager";

  tools = with pkgs; [
    # Toolchain: GNU Fortran and fpm
    gfortran
    fpm

    # Language server
    fortls

    # Formatter
    fprettify

  ];

  semgrep = true;
  trivy = true;

  lint = ''
    when fpm.toml fpm build
    run_on '*.f90' fprettify --diff
  '';

  fmt = ''
    run_on '*.f90' fprettify --indent 2
  '';

  tests = {
    run = [
      ''
        when fpm.toml fpm test
      ''
    ];
  };
}
