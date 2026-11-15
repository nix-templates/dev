# Julia.
{ pkgs, ... }:
{
  description = "Julia development environment for scientific computing";

  tools = with pkgs; [
    # Toolchain: Julia's package manager, REPL and test runner
    julia

    # Documents and plots
    pandoc

  ];

  trivy = true;

  lint = ''
    when Project.toml julia --project=. -e 'using Pkg; Pkg.status()'
  '';

  fmt = ''
    run typos --write-changes .
  '';

  tests = {
    run = [
      ''
        when test/runtests.jl julia --project=. -e 'using Pkg; Pkg.test()'
      ''
    ];
    coverage = [
      ''
        when test/runtests.jl julia --project=. -e 'using Pkg; Pkg.test(coverage=true)'
      ''
    ];
  };
}
