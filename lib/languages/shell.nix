# Shell-script.
{ pkgs, ... }:
{
  description = "Shell-script development environment: bash-language-server, ShellCheck, shfmt and bats";

  tools = with pkgs; [
    # Toolchain and test runner
    bash
    bats

    # Language server
    bash-language-server

    # Linter
    shellcheck

    # Formatter
    shfmt

    # Tests: bats is above; shellspec is the other common runner
    shellspec
  ];

  semgrep = true;
  trivy = true;

  # A shell script is a *.sh or *.bash file, or a file with no extension whose
  # first line names a shell: tools often have no extension.
  lint = ''
    on_shell_scripts shellcheck --external-sources
    on_shell_scripts shfmt -d -i 2 -ci
  '';

  fmt = ''
    on_shell_scripts shfmt -w -i 2 -ci
  '';

  tests = {
    run = [
      ''
        run_on '*.bats' bats
      ''
      ''
        when .shellspec shellspec
      ''
    ];
  };
}
