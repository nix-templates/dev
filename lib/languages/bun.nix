# Bun.
{ pkgs, ... }:
{
  description = "Bun development environment: tsserver, Biome, oxlint and Prettier";

  tools = with pkgs; [
    # Toolchain: Bun, plus Node for tools that still expect it
    bun
    nodejs
    typescript

    # Language servers
    typescript-language-server
    vscode-langservers-extracted

    # Linters
    biome
    oxlint

    # Formatters
    prettier

  ];

  semgrep = true;
  trivy = true;

  lint = ''
    when tsconfig.json tsc --noEmit
    run oxlint .
    when biome.json biome check .
  '';

  fmt = ''
    run prettier --write --ignore-unknown --log-level warn .
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
