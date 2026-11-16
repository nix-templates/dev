# Pulumi.
{
  pkgs,
  lib,
  ...
}:
{
  description = "Pulumi environment with the Python, Go, Node and JVM SDKs plus IaC scanners";

  # A Pulumi project has Pulumi.yaml.
  marks = [
    "Pulumi.yaml"
  ];

  tools = with pkgs; [
    # Pulumi, plus its watch/analyzer/language/resource plugins
    pulumi-bin

    # SDK runtimes
    python313
    go
    nodejs
    jdk
    maven

    # Language servers for the SDK languages you actually use
    gopls
    basedpyright
    typescript-language-server

    # Linters and formatters per SDK language
    ruff
    golangci-lint
    gofumpt
    prettier

    # Cluster and shell helpers
    kubectl
    jq

    # Security: infrastructure-as-code and dependency scanning
    checkov

  ];

  # The same requirements as data, for consumers that construct a package set.
  packageConfig = {
    allowInsecurePredicate = pkg: lib.getName pkg == "ecdsa";
  };

  # What the project's nixpkgs has to allow before these tools evaluate.
  nixpkgsConfig = [
    ''config.allowInsecurePredicate = pkg: inputs.nixpkgs.lib.getName pkg == "ecdsa";''
  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when go.mod golangci-lint run ./...
    when_any '*.py' ruff check .
  '';

  style = ''
    run gofumpt -l -w .
    when_any '*.py' ruff format .
    run prettier --write --ignore-unknown --log-level warn .
  '';

  security = ''
    run checkov --quiet --compact --directory .
  '';
}
