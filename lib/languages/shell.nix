# Shell scripts.
{ pkgs, ... }:
{
  tools = with pkgs; [
    bash
    bats
    bash-language-server
    shellcheck
    shfmt
  ];

  semgrep = true;

  lint = ''
    run_on '*.sh' shellcheck --external-sources
    run_on '*.bash' shellcheck --external-sources
    run_on '*.sh' shfmt -d -i 2 -ci
  '';

  fmt = ''
    run_on '*.sh' shfmt -w -i 2 -ci
    run_on '*.bash' shfmt -w -i 2 -ci
  '';

  fmtCheck = ''
    run_on '*.sh' shfmt -d -i 2 -ci
    run_on '*.bash' shfmt -d -i 2 -ci
  '';
}
