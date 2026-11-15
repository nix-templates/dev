# Elm.
{ pkgs, ... }:
{
  description = "Elm development environment: elm-language-server, elm-review, elm-format and elm-test";

  tools = with pkgs; [
    # Toolchain
    elmPackages.elm
    elmPackages.elm-json
    elm2nix

    # Language server
    elmPackages.elm-language-server

    # Linter and test runner
    elmPackages.elm-review
    elmPackages.elm-test

    # Formatter
    elmPackages.elm-format

    # Node.js, which several Elm tools shell out to
    nodejs

    # Tests
    elmPackages.elm-test
  ];

  semgrep = true;
  trivy = true;

  lint = ''
    when src elm-format --validate src
    when review/elm.json elm-review
  '';

  fmt = ''
    when src elm-format --yes src
  '';

  tests = {
    run = [
      ''
        if [ -e elm.json ] && [ -d tests ]; then
          run elm-test
        fi
      ''
    ];
  };
}
