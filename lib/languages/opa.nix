# Open Policy Agent.
{ pkgs, ... }:
{
  description = "Open Policy Agent environment: Regal (linter + LSP), Conftest and opa fmt";

  tools = with pkgs; [
    # Toolchain: opa fmt, opa test and opa eval
    open-policy-agent
    conftest

    # Language server and linter in one binary
    regal

  ];

  trivy = true;

  quality = ''
    when_any '*.rego' regal lint .
    when_any '*.rego' opa check .
    when_any '*.rego' opa fmt --fail --list .
  '';

  style = ''
    when_any '*.rego' opa fmt --write .
  '';

  tests = {
    run = [
      ''
        when_any '*_test.rego' opa test . --fail-on-empty
      ''
    ];
  };
}
