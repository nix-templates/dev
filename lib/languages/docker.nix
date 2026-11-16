# Container.
{ pkgs, ... }:
{
  description = "Container environment: dockerfile-language-server, Hadolint, Trivy and Dive";

  # Dockerfiles and Compose files.
  marks = [
    "Dockerfile"
    "Dockerfile.*"
    "*.dockerfile"
    "Containerfile"
    "compose.yaml"
    "compose.yml"
    "docker-compose.yaml"
    "docker-compose.yml"
  ];

  tools = with pkgs; [
    # Container tooling and rootless runtimes
    docker-compose
    docker-buildx
    podman
    buildah
    skopeo
    dive

    # Language servers for Dockerfiles and Compose files
    dockerfile-language-server-nodejs
    yaml-language-server

    # Linters
    hadolint
    yamllint
    container-structure-test

    # Formatter for Compose and CI YAML
    yamlfmt

    # Security: image, filesystem, SBOM and signature tooling
    trivy
    grype
    syft
    cosign

  ];

  quality = ''
    for_each 'Dockerfile*' hadolint
    run yamllint --strict .
  '';

  style = ''
    run yamlfmt .
  '';

  security = ''
    run trivy config --exit-code 1 --skip-dirs .direnv .
    run trivy fs --scanners vuln,secret --no-progress --exit-code 1 .
  '';
}
