# GitHub Actions.
{ pkgs, ... }:
{
  description = "GitHub Actions environment: actionlint, zizmor, act and the GitHub CLI";

  # Workflows.
  marks = [
    ".github/workflows/*.yml"
    ".github/workflows/*.yaml"
  ];

  tools = with pkgs; [
    # Toolchain: run workflows locally and talk to the API
    act
    gh

    # Language server for workflow YAML
    yaml-language-server

    # Linters
    actionlint
    yamllint

    # Formatter
    yamlfmt

    # Security: zizmor is the dedicated GitHub Actions SAST tool
    zizmor
    trivy

  ];

  quality = ''
    when .github/workflows actionlint
    run yamllint --strict .
  '';

  style = ''
    run yamlfmt .
  '';

  security = ''
    when .github/workflows zizmor --persona regular .github/workflows
  '';
}
