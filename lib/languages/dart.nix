# Dart and Flutter.
{ pkgs, ... }:
{
  description = "Dart and Flutter development environment; the Dart SDK provides the LSP, linter and formatter";

  tools = with pkgs; [
    # Toolchain: dart analyze, dart format and the LSP all ship with the SDK
    dart
    flutter

  ];

  semgrep = true;
  trivy = true;

  lint = ''
    when pubspec.yaml dart analyze --fatal-infos
    run dart format --output=none --set-exit-if-changed .
  '';

  fmt = ''
    run dart format .
  '';

  scan = ''
    when pubspec.lock dart pub outdated
  '';

  arch = [
    ''
      when_has pubspec.yaml dependency_validator dart run dependency_validator
    ''
  ];

  tests = {
    run = [
      ''
        if has flutter_test pubspec.yaml; then
          run flutter test
        elif [ -e pubspec.yaml ] && [ -d test ]; then
          run dart test
        fi
      ''
    ];
    coverage = [
      ''
        when_has pubspec.yaml flutter_test flutter test --coverage
      ''
    ];
  };
}
