# Crystal.
{ pkgs, ... }:
{
  description = "Crystal development environment: Crystalline, Ameba and crystal tool format";

  tools = with pkgs; [
    # Toolchain
    crystal
    shards

    # Language server
    crystalline

    # Linter
    ameba

  ];

  semgrep = true;
  trivy = true;

  lint = ''
    when_any '*.cr' ameba
    run crystal tool format --check
  '';

  fmt = ''
    run crystal tool format
  '';

  tests = {
    run = [
      ''
        when spec crystal spec --order random
      ''
    ];
  };
}
