# R.
{ pkgs, ... }:
let
  # rWrapper bakes the R packages into the R installation itself, which is what
  # makes `library(languageserver)` work without any per-project installs.
  rEnv = pkgs.rWrapper.override {
    packages = with pkgs.rPackages; [
      covr
      knitr
      languageserver
      lintr
      rmarkdown
      styler
      testthat
    ];
  };

  tools = with pkgs; [
    # R with languageserver, lintr and styler baked in
    rEnv

    # Document rendering for knitr / R Markdown
    pandoc
    texlive.combined.scheme-full

  ];
in
{
  description = "R development environment: languageserver, lintr and styler";

  inherit tools;

  trivy = true;

  quality = ''
    run Rscript -e 'lintr::lint_dir(".")'
  '';

  style = ''
    run Rscript -e 'styler::style_dir(".")'
  '';

  tests = {
    run = [
      ''
        when tests/testthat Rscript -e 'testthat::test_local(stop_on_failure = TRUE)'
      ''
    ];
    coverage = [
      ''
        when tests/testthat Rscript -e 'print(covr::package_coverage())'
      ''
    ];
  };
}
