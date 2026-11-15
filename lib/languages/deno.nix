# Deno.
{ pkgs, ... }:
{
  description = "Deno development environment with Deno's built-in LSP, linter and formatter";

  tools = with pkgs; [
    # Toolchain: Deno bundles its own LSP, linter, formatter and test runner
    deno

  ];

  semgrep = true;
  trivy = true;

  lint = ''
    run deno lint
    when deno.json deno check .
  '';

  fmt = ''
    run deno fmt
  '';

  tests = {
    run = [
      ''
        when_any 'deno.json*' deno test
      ''
    ];
    coverage = [
      ''
        deno_coverage() {
          deno test --coverage=coverage/ && deno coverage coverage/
        }
        when_any 'deno.json*' deno_coverage
      ''
    ];
    bench = [
      ''
        when_any 'deno.json*' deno bench
      ''
    ];
  };
}
