# TypeScript.
{ pkgs, ... }:
{
  description = "TypeScript development environment: tsserver, Biome, ESLint and strict type checking";

  # TypeScript files or a tsconfig.json; the project is then not also read as plain Node.js.
  marks = [
    "*.ts"
    "*.tsx"
    "*.mts"
    "*.cts"
    "tsconfig.json"
  ];
  insteadOf = [
    "node"
  ];

  tools = with pkgs; [
    # Toolchain
    nodejs
    pnpm
    typescript

    # Language servers
    typescript-language-server
    vscode-langservers-extracted

    # Linters: Biome is the single fast lint+format binary, ESLint the ecosystem standard
    biome
    eslint
    oxlint

    # Formatters
    prettier
    prettierd

  ];

  semgrep = true;
  trivy = true;

  lint = ''
    when tsconfig.json tsc --noEmit
    when biome.json biome check .
    when eslint.config.js eslint .
    run oxlint .
  '';

  fmt = ''
    when biome.json biome format --write .
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
