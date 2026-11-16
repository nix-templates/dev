# Groovy.
{ pkgs, ... }:
{
  description = "Groovy development environment: groovy-language-server and npm-groovy-lint";

  tools = with pkgs; [
    # Toolchain
    groovy
    gradle
    jdk

    # Language server
    groovy-language-server

    # Linter and formatter in one (CodeNarc under the hood)
    npm-groovy-lint

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when_any '*.groovy' npm-groovy-lint --failon warning .
  '';

  style = ''
    when_any '*.groovy' npm-groovy-lint --format .
  '';

  architecture = [
    ''
      when_has pom.xml maven-enforcer-plugin mvn -B -q enforcer:enforce
    ''
    ''
      if has com.autonomousapps.dependency-analysis build.gradle build.gradle.kts settings.gradle settings.gradle.kts; then
        run gradle --no-daemon -q buildHealth
      fi
    ''
  ];

  tests = {
    run = [
      ''
        when pom.xml mvn -B test
      ''
      ''
        if [ -e build.gradle ] || [ -e build.gradle.kts ]; then
          run gradle --no-daemon test
        fi
      ''
    ];
    coverage = [
      ''
        if has jacoco build.gradle build.gradle.kts settings.gradle settings.gradle.kts; then
          run gradle --no-daemon test jacocoTestCoverageVerification
        fi
      ''
    ];
  };
}
