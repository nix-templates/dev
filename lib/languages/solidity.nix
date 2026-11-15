# Solidity.
{ pkgs, ... }:
{
  description = "Solidity environment: solc, Foundry and the Slither static analyser";

  tools = with pkgs; [
    # Toolchain: the compiler, version manager and the Foundry suite
    solc
    solc-select
    foundry

    # Node.js, for Hardhat and solhint
    nodejs
    pnpm

    # Security: Slither is the standard Solidity SAST tool
    slither-analyzer

  ];

  semgrep = true;
  trivy = true;

  lint = ''
    when foundry.toml forge build --sizes
    if_have solhint solhint 'contracts/**/*.sol'
  '';

  fmt = ''
    when foundry.toml forge fmt
  '';

  scan = ''
    when foundry.toml slither . --exclude-dependencies
  '';

  tests = {
    run = [
      ''
        when foundry.toml forge test
      ''
    ];
    coverage = [
      ''
        when foundry.toml forge coverage
      ''
    ];
    bench = [
      ''
        when .gas-snapshot forge snapshot --check
      ''
    ];
  };
}
