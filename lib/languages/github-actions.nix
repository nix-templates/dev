# GitHub Actions.
{ pkgs, ... }:
{
  description = "GitHub Actions environment: actionlint, zizmor, act and the GitHub CLI";

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

  lint = ''
    when .github/workflows actionlint
    run yamllint --strict .
  '';

  fmt = ''
    run yamlfmt .
  '';

  scan = ''
    when .github/workflows zizmor --persona regular .github/workflows
  '';
}
