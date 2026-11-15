# Python. `python` picks the interpreter; the default is the project's python3.
{ pkgs, options, ... }:
let
  python = options.python or pkgs.python3;
in
{
  tools = [
    python
    python.pkgs.pip
    pkgs.uv

    # Language server and type checkers
    pkgs.basedpyright
    pkgs.mypy

    # Linter and formatter
    pkgs.ruff
    python.pkgs.vulture

    # Security: SAST
    pkgs.bandit
  ];

  semgrep = true;

  lint = ''
    run ruff check .
    when pyproject.toml mypy .
    run vulture . --min-confidence 80 --exclude '.venv,.direnv,build,dist'
  '';

  fmt = ''
    run ruff check --select I --fix .
    run ruff format .
  '';

  fmtCheck = ''
    run ruff check --select I .
    run ruff format --check .
  '';

  scan = ''
    run bandit --quiet --recursive . --exclude ./.venv,./.direnv
  '';
}
