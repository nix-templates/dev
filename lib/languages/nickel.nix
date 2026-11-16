# Nickel.
{ pkgs, ... }:
{
  description = "Nickel development environment with the nls language server";

  tools = with pkgs; [
    # Toolchain: nickel formats and typechecks on its own
    nickel

    # Language server
    nls

  ];

  trivy = true;

  quality = ''
    run_on '*.ncl' nickel format --check
  '';

  style = ''
    run_on '*.ncl' nickel format --in-place
  '';
}
