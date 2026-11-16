{ ... }:
{
  defaults.pythonProjectEnvironment = true;
  replace.python = [
    "quality"
    "tests"
  ];
  # FastAPI's TestClient and async fixtures are application dependencies. Use
  # the project's pytest and plugins rather than Nix's Python environment.
  quality = import ./python-quality.nix "--extend-select FAST";
  tests.run = [ "run project_python -m pytest -q" ];
}
