# Deno.
{ pkgs, ... }:
{
  description = "Deno development environment with Deno's built-in LSP, linter and formatter";

  # A Deno project has deno.json, and is then not also read as Node.js, TypeScript or Bun.
  marks = [
    "deno.json"
    "deno.jsonc"
  ];
  insteadOf = [
    "node"
    "typescript"
    "bun"
  ];

  tools = with pkgs; [
    # Toolchain: Deno bundles its own LSP, linter, formatter and test runner
    deno

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    run deno lint
    when deno.json deno check .
  '';

  style = ''
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
