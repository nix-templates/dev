# HashiCorp.
{
  pkgs,
  lib,
  ...
}:
{
  description = "HashiCorp environment: Terraform, Vault, Nomad, Consul, Packer and their linters";

  # Never found by itself: Terraform files are read as the terraform language, which uses OpenTofu.
  # The HashiCorp binaries are unfree, so a project asks for them by name.
  marks = [ ];

  tools = with pkgs; [
    # The HashiCorp stack
    terraform
    vault
    nomad
    consul
    packer
    terragrunt
    nomad-autoscaler
    nomad-pack
    levant
    damon

    # Language server
    terraform-ls

    # Linters and documentation
    tflint
    terraform-docs

    # Security: infrastructure-as-code SAST
    tfsec
    checkov
    trivy

  ];

  # The same requirements as data, for consumers that construct a package set.
  packageConfig = {
    allowUnfree = true;
    allowInsecurePredicate = pkg: lib.getName pkg == "ecdsa";
  };

  # What the project's nixpkgs has to allow before these tools evaluate.
  nixpkgsConfig = [
    "config.allowUnfree = true;"
    ''config.allowInsecurePredicate = pkg: inputs.nixpkgs.lib.getName pkg == "ecdsa";''
  ];

  quality = ''
    when_any '*.tf' terraform fmt -check -recursive
    when_any '*.tf' tflint --recursive
    when_any '*.pkr.hcl' packer fmt -check -recursive .
  '';

  style = ''
    when_any '*.tf' terraform fmt -recursive
  '';

  security = ''
    when_any '*.tf' tfsec --soft-fail=false .
    when_any '*.tf' checkov --quiet --compact --directory .
  '';

  tests = {
    run = [
      ''
        terraform_tests() {
          terraform init -backend=false && terraform test
        }
        when_any '*.tftest.hcl' terraform_tests
      ''
    ];
  };
}
