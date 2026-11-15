# Perl.
{ pkgs, ... }:
{
  description = "Perl development environment: PerlNavigator, Perl::Critic and Perl::Tidy";

  tools = with pkgs; [
    # Toolchain
    perl

    # Language servers
    perlnavigator
    perlPackages.PLS

    # Linter
    perlPackages.PerlCritic

    # Formatter
    perlPackages.PerlTidy

  ];

  semgrep = true;
  trivy = true;

  lint = ''
    run_on '*.pl' perlcritic --severity 3
    run_on '*.pm' perlcritic --severity 3
  '';

  fmt = ''
    run_on '*.pl' perltidy --backup-and-modify-in-place --backup-file-extension=/
    run_on '*.pm' perltidy --backup-and-modify-in-place --backup-file-extension=/
  '';

  tests = {
    run = [
      ''
        when t prove -lr t
      ''
    ];
  };
}
