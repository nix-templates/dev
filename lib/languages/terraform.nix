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

  # The same requirements as data, for consumers that construct a package set.
  packageConfig = {
    allowInsecurePredicate = pkg: lib.getName pkg == "ecdsa";
  };

  # What the project's nixpkgs has to allow before these tools evaluate.
  nixpkgsConfig = [
    ''config.allowInsecurePredicate = pkg: inputs.nixpkgs.lib.getName pkg == "ecdsa";''
  ];

  quality = ''
    when_any '*.tf' tofu fmt -check -recursive
    when_any '*.tf' tflint --recursive
  '';

  style = ''
    when_any '*.tf' tofu fmt -recursive
  '';

  security = ''
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
