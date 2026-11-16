# Swift.
{ pkgs, ... }:
{
  description = "Swift development environment: SourceKit-LSP, SwiftLint and SwiftFormat";

  tools = with pkgs; [
    # Toolchain
    swift

    # Language server
    sourcekit-lsp

    # Linter
    swiftlint

    # Formatter
    swiftformat

  ];

  semgrep = true;
  trivy = true;

  # The shell needs a C compiler and its wrapper.
  needsCC = true;

  quality = ''
    when_any '*.swift' swiftlint lint --quiet
    run swiftformat --lint .
  '';

  style = ''
    run swiftformat .
  '';

  architecture = [
    ''
      # Periphery finds unused declarations. nixpkgs has it for macOS only, so it
      # runs when it is on PATH.
      if [ -e .periphery.yml ]; then
        if_have periphery periphery scan --strict
      fi
    ''
  ];

  tests = {
    run = [
      ''
        when Package.swift swift test
      ''
    ];
    coverage = [
      ''
        when Package.swift swift test --enable-code-coverage
      ''
    ];
  };
}
