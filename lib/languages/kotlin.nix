# Kotlin.
{ pkgs, ... }:
{
  description = "Kotlin development environment: kotlin-language-server, ktlint, detekt and ktfmt";

  tools = with pkgs; [
    # Toolchain and build systems
    kotlin
    gradle
    jdk

    # Language server
    kotlin-language-server

    # Linters and static analysis
    ktlint
    detekt

    # Formatters (ktlint can also format; ktfmt follows the Google style)
    ktfmt

    # Native bits some JVM tooling links against
    gcc
    ncurses
    patchelf
    zlib

  ];

  semgrep = true;
  trivy = true;

  lint = ''
    when_any '*.kt' ktlint --relative
    when_any '*.kt' detekt --build-upon-default-config
  '';

  fmt = ''
    when_any '*.kt' ktlint --format --relative
  '';

  arch = [
    ''
      if has com.autonomousapps.dependency-analysis build.gradle build.gradle.kts settings.gradle settings.gradle.kts; then
        run gradle --no-daemon -q buildHealth
      fi
    ''
  ];

  tests = {
    run = [
      ''
        if [ -e build.gradle ] || [ -e build.gradle.kts ]; then
          run gradle --no-daemon test
        fi
      ''
    ];
    coverage = [
      ''
        if has kotlinx.kover build.gradle build.gradle.kts settings.gradle settings.gradle.kts; then
          run gradle --no-daemon koverVerify
        fi
      ''
    ];
    mutation = [
      ''
        if has info.solidsoft.pitest build.gradle build.gradle.kts settings.gradle settings.gradle.kts; then
          run gradle --no-daemon pitest
        fi
      ''
    ];
  };
}
