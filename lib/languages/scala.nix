# Scala.
{ pkgs, ... }:
{
  description = "Scala development environment: Metals, Scalafmt and Scalafix";

  tools = with pkgs; [
    # Toolchain and build tools
    scala
    sbt
    scala-cli
    mill
    coursier
    jdk

    # Language server
    metals

    # Linter / refactoring engine
    scalafix

    # Formatter
    scalafmt

  ];

  semgrep = true;
  trivy = true;

  lint = ''
    when .scalafmt.conf scalafmt --test
    when .scalafix.conf scalafix --check
  '';

  fmt = ''
    when .scalafmt.conf scalafmt
  '';

  arch = [
    ''
      when_has project/plugins.sbt sbt-explicit-dependencies sbt undeclaredCompileDependenciesTest unusedCompileDependenciesTest
    ''
  ];

  tests = {
    run = [
      ''
        when build.sbt sbt test
      ''
      ''
        when build.mill mill __.test
      ''
      ''
        when project.scala scala-cli test .
      ''
    ];
    coverage = [
      ''
        when_has project/plugins.sbt sbt-scoverage sbt clean coverage test coverageReport
      ''
    ];
    mutation = [
      ''
        when_has project/plugins.sbt stryker4s sbt stryker
      ''
    ];
  };
}
