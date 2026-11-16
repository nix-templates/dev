# Clojure.
{ pkgs, ... }:
{
  description = "Clojure development environment: clojure-lsp, clj-kondo, cljfmt and Babashka";

  tools = with pkgs; [
    # Toolchain: the CLI, Leiningen, Boot and Babashka for scripting
    clojure
    leiningen
    boot
    babashka

    # Language server
    clojure-lsp

    # Linter
    clj-kondo

    # Formatters
    cljfmt
    zprint

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when_any '*.clj' clj-kondo --lint .
    run cljfmt check .
  '';

  style = ''
    run cljfmt fix .
  '';

  tests = {
    run = [
      ''
        when project.clj lein test
      ''
      ''
        when_has deps.edn :test clojure -M:test
      ''
    ];
    coverage = [
      ''
        when_has project.clj cloverage lein cloverage
      ''
    ];
  };
}
