metadata:
{ lib, ... }:
let
  isDocs = metadata.distribution == "mkdocs";
  isScrapy = metadata.distribution == "scrapy";
in
{
  defaults.pythonProjectEnvironment = true;
  replace.python = [
    "quality"
    "tests"
  ];
  quality =
    (import ./python-quality.nix "")
    + lib.optionalString isDocs ''
      run project_python -m mkdocs build --strict
    '';
  tests.run = [
    (
      if isDocs then
        "run project_python -m mkdocs build --strict"
      else if isScrapy then
        "run project_python -m scrapy check"
      else
        "run project_python -m pytest -q"
    )
  ];
}
