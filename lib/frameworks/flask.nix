{ pkgs, ... }:
let
  isolated = import ./isolated.nix { inherit pkgs; };
  templateTool = isolated "flask-templates" pkgs.djlint "djlint";
in
{
  tools = [ templateTool ];
  defaults.pythonProjectEnvironment = true;
  replace.python = [
    "quality"
    "tests"
  ];
  quality = (import ./python-quality.nix "") + ''
    when_any '*.html' ${templateTool}/bin/dvt-flask-templates . --profile jinja --lint
  '';
  style = ''
    when_any '*.html' ${templateTool}/bin/dvt-flask-templates . --profile jinja --reformat
  '';
  tests.run = [ "run project_python -m pytest -q" ];
}
