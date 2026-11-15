# What every project gets, whatever its languages: spelling, editorconfig,
# secrets, and the scanners that read any source tree.
{ pkgs, ... }:
{
  tools = with pkgs; [
    gitleaks
    typos
    editorconfig-checker
    trivy
  ];

  lint = ''
    run typos --format brief .
    run editorconfig-checker -format gcc -exclude '(^|/)(\.direnv|\.venv|\.git|node_modules|vendor|result|dist|build|target)/'
  '';

  scan = ''
    run trivy fs --scanners vuln,secret --no-progress --skip-dirs .direnv --skip-dirs .venv .
    run gitleaks dir . --no-banner --redact
  '';
}
