# GraphQL.
{ pkgs, ... }:
{
  description = "GraphQL environment: graphql-language-service-cli, ESLint and Prettier";

  tools = with pkgs; [
    # Toolchain
    nodejs
    pnpm
    typescript

    # Language servers
    graphql-language-service-cli
    typescript-language-server

    # Linters
    eslint
    biome

    # Formatters
    prettier

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when .graphqlrc.yml graphql-lsp validate
    when eslint.config.js eslint .
  '';

  style = ''
    run prettier --write --ignore-unknown --log-level warn .
  '';

  architecture = [
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
