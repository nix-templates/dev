# Node.js.
{ pkgs, ... }:
let
  nodejs = pkgs.nodejs;
  yarn = pkgs.yarn.override { inherit nodejs; };

  tools = with pkgs; [
    # Toolchain: runtime, the three package managers and the TS compiler
    nodejs
    pnpm
    yarn
    typescript

    # Language servers (vscode-langservers-extracted covers JSON/HTML/CSS/ESLint)
    typescript-language-server
    vscode-langservers-extracted

    # Linters: ESLint is the standard, oxlint and Biome are the fast alternatives
    eslint
    oxlint
    biome

    # Formatters
    prettier
    prettierd

  ];
in
{
  description = "Node.js development environment: typescript-language-server, ESLint, Prettier and Biome";

  inherit tools;

  semgrep = true;
  trivy = true;

  lint = ''
    when eslint.config.js eslint .
    when eslint.config.mjs eslint .
    run oxlint .
    when biome.json biome check .
  '';

  fmt = ''
    run prettier --write --ignore-unknown --log-level warn .
  '';

  scan = ''
    when package-lock.json npm audit --audit-level=high
  '';

  layers = [
    ''
      depcruise_sources() {
        if [ -d src ]; then
          js_exec depcruise src
        else
          js_exec depcruise .
        fi
      }
      when_any '.dependency-cruiser.*' depcruise_sources
    ''
    ''
      if found 'knip.*' '.knip.*'; then
        run js_exec knip --no-progress
      fi
    ''
  ];

  tests = {
    run = [
      ''
        if has '"test":' package.json; then
          run "$(js_pm)" run test
        fi
      ''
    ];
    coverage = [
      ''
        when_any 'vitest.config.*' js_exec vitest run --coverage
      ''
    ];
    mutation = [
      ''
        if found 'stryker.config.*' 'stryker.conf.*'; then
          run js_exec stryker run
        fi
      ''
    ];
    browser = [
      ''
        when_any 'playwright.config.*' js_exec playwright test --forbid-only
      ''
    ];
  };
}
