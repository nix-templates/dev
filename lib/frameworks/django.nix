{
  pkgs,
  lib,
  options,
  ...
}:
let
  manage = lib.escapeShellArg (options.django.managePy or "manage.py");
  isolated = import ./isolated.nix { inherit pkgs; };
  templateTool = isolated "django-templates" pkgs.djlint "djlint";
  pythonTool = isolated "django-python" pkgs.ruff "ruff";
  runner = options.django.testRunner or "django";
in
assert lib.assertMsg (builtins.elem runner [
  "django"
  "pytest"
]) "django.testRunner must be 'django' or 'pytest'";
{
  # Framework runtime code always uses the project's interpreter. These tools
  # have their own Nix environments and never install Django into the project.
  tools = [
    templateTool
    pythonTool
  ];
  defaults.pythonProjectEnvironment = true;
  replace.python = [
    "quality"
    "tests"
  ];

  quality = (import ./python-quality.nix "") + ''
    run ${pythonTool}/bin/dvt-django-python check --extend-select DJ .
    when_any '*.html' ${templateTool}/bin/dvt-django-templates . --profile django --lint
    run project_python ${manage} check
    run project_python ${manage} makemigrations --check --dry-run
  '';
  style = ''
    when_any '*.html' ${templateTool}/bin/dvt-django-templates . --profile django --reformat
  '';
  security = ''
    run project_python ${manage} check --deploy --fail-level WARNING
  '';
  tests.run = [
    (
      if runner == "django" then
        ''
          run project_python ${manage} test --noinput
        ''
      else
        ''
          run project_python -m pytest -q
        ''
    )
  ];
}
