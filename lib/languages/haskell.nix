# Haskell.
{ pkgs, ... }:
{
  description = "Haskell development environment: HLS, HLint, Ormolu and cabal-fmt";

  tools = with pkgs; [
    # Toolchain
    ghc
    cabal-install
    stack
    haskellPackages.hoogle

    # Language server
    haskell-language-server

    # Linter
    hlint

    # Formatters
    ormolu
    haskellPackages.cabal-fmt

    # Architecture: dead code and unused exports, from weeder.toml
    haskellPackages.weeder
  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when_any '*.hs' hlint .
    run_on '*.hs' ormolu --mode check
  '';

  style = ''
    run_on '*.hs' ormolu --mode inplace
    run_on '*.cabal' cabal-fmt --inplace
  '';

  architecture = [
    ''
      when weeder.toml weeder
    ''
  ];

  tests = {
    run = [
      ''
        if [ -e stack.yaml ]; then
          run stack test
        else
          when_any '*.cabal' cabal test all --test-show-details=direct
        fi
      ''
    ];
    coverage = [
      ''
        when_any '*.cabal' cabal test all --enable-coverage
      ''
    ];
    bench = [
      ''
        when_any '*.cabal' cabal bench all
      ''
    ];
  };
}
