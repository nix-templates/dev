# What every project gets, whatever its languages: spelling, editorconfig and
# secret scanning, and the formatter for the flake itself. semgrep and trivy
# join when one of the project's languages asks for them.
{ pkgs, ... }:
{
  tools = with pkgs; [
    gitleaks
    typos
    editorconfig-checker
    nixfmt
  ];

  lint = ''
    run typos --format brief .
    run editorconfig-checker -format gcc -exclude '(^|/)(\.direnv|\.venv|\.git|node_modules|vendor|result|dist|build|target)/'
  '';

  scan = ''
    run gitleaks dir . --no-banner --redact
  '';
}
