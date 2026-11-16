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

  quality = ''
    run typos --format brief .
    # The indent size is left to each language's formatter: this check cannot
    # tell a line that is aligned with an opening bracket from one that is
    # indented wrong.
    run editorconfig-checker -format gcc -no-color -disable-indent-size -exclude '(^|/)(\.direnv|\.venv|\.git|node_modules|vendor|result|dist|build|target)/'
  '';

  security = ''
    # --verbose names each finding's file, line and rule; the secret stays redacted.
    run gitleaks dir . --no-banner --redact --verbose
  '';
}
