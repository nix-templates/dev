# Terraform.
{
  pkgs,
  lib,
  ...
}:
{
  description = "Terraform environment: terraform-ls, TFLint, tfsec, Checkov and terraform-docs";

  tools = with pkgs; [
    # Toolchain: OpenTofu is the freely licensed Terraform drop-in
    opentofu
    terragrunt

    # Language server
    terraform-ls

    # Linters and documentation
    tflint
    terraform-docs

    # Security: infrastructure-as-code SAST and misconfiguration scanning
    tfsec
    checkov
    trivy

  ];

  # What the project's nixpkgs has to allow before these tools evaluate.
  nixpkgsConfig = [
    ''config.allowInsecurePredicate = pkg: inputs.nixpkgs.lib.getName pkg == "ecdsa";''
  ];

  lint = ''
    when_any '*.tf' tofu fmt -check -recursive
    when_any '*.tf' tflint --recursive
  '';

  fmt = ''
    when_any '*.tf' tofu fmt -recursive
  '';

  scan = ''
    when_any '*.tf' tfsec --soft-fail=false .
    when_any '*.tf' checkov --quiet --compact --directory .
    run trivy config --exit-code 1 --skip-dirs .direnv .
  '';

  tests = {
    run = [
      ''
        tofu_tests() {
          tofu init -backend=false && tofu test
        }
        when_any '*.tftest.hcl' tofu_tests
      ''
    ];
  };
}
