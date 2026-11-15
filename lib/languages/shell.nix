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

  lint = ''
    run_on '*.sh' shellcheck --external-sources
    run_on '*.bash' shellcheck --external-sources
    run_on '*.sh' shfmt -d -i 2 -ci
  '';

  fmt = ''
    run_on '*.sh' shfmt -w -i 2 -ci
    run_on '*.bash' shfmt -w -i 2 -ci
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
