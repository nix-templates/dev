# Java.
{ pkgs, ... }:
{
  description = "Java development environment: Eclipse JDT language server, Checkstyle, PMD and google-java-format";

  tools = with pkgs; [
    # Toolchain and build systems
    jdk
    maven
    gradle

    # Language server
    jdt-language-server

    # Linters and static analysis
    checkstyle
    pmd

    # Formatter
    google-java-format

    # Native bits some JVM tooling links against
    gcc
    ncurses
    patchelf
    zlib

  ];

  semgrep = true;
  trivy = true;

  shellHook = ''
    # Load Lombok into every JVM this shell starts, so annotation processing
    # works in javac, Maven, Gradle and the language server alike.
    export JAVA_TOOL_OPTIONS="-javaagent:${pkgs.lombok}/share/java/lombok.jar''${JAVA_TOOL_OPTIONS:+ $JAVA_TOOL_OPTIONS}"
  '';

  lint = ''
    when_any '*.java' checkstyle -c /google_checks.xml .
    when_any '*.java' pmd check --dir . --rulesets rulesets/java/quickstart.xml --format text --no-cache
  '';

  fmt = ''
    run_on '*.java' google-java-format --replace
  '';

  layers = [
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
        when_has pom.xml jacoco-maven-plugin mvn -B verify
      ''
      ''
        if has jacoco build.gradle build.gradle.kts settings.gradle settings.gradle.kts; then
          run gradle --no-daemon test jacocoTestCoverageVerification
        fi
      ''
    ];
    mutation = [
      ''
        when_has pom.xml pitest-maven mvn -B org.pitest:pitest-maven:mutationCoverage
      ''
      ''
        if has info.solidsoft.pitest build.gradle build.gradle.kts settings.gradle settings.gradle.kts; then
          run gradle --no-daemon pitest
        fi
      ''
    ];
  };
}
