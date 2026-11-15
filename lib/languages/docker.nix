# Container.
{ pkgs, ... }:
{
  description = "Container environment: dockerfile-language-server, Hadolint, Trivy and Dive";

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

  lint = ''
    for_each 'Dockerfile*' hadolint
    run yamllint --strict .
  '';

  fmt = ''
    run yamlfmt .
  '';

  scan = ''
    run trivy config --no-progress --skip-dirs .direnv .
    run trivy fs --scanners vuln,secret --no-progress .
  '';
}
