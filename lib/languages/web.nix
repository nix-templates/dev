# Web front-end.
{ pkgs, ... }:
{
  description = "Web front-end environment: HTML/CSS/Tailwind language servers, ESLint, Stylelint and Prettier";

  # Pages and stylesheets. JavaScript alone is Node.js or TypeScript.
  marks = [
    "*.html"
    "*.css"
    "*.scss"
  ];

  tools = with pkgs; [
    # Toolchain
    nodejs
    pnpm
    typescript

    # Language servers for TS, HTML, CSS, JSON, Tailwind and Emmet
    typescript-language-server
    vscode-langservers-extracted
    tailwindcss-language-server
    emmet-language-server

    # Linters for scripts, stylesheets and markup
    eslint
    stylelint
    htmlhint
    biome

    # Formatters and asset tooling
    prettier
    svgo

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when eslint.config.js eslint .
    when .stylelintrc.json stylelint '**/*.{css,scss}'
    run_on '*.html' htmlhint
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
