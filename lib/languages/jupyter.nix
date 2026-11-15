# Jupyter.
{
  pkgs,
  lib,
  options,
  ...
}:
let
  python = options.python or pkgs.python313;

  # The interpreter with the test tools in it, so that `python -m pytest` finds
  # them. Separate packages on PATH would not see each other.
  interpreter = python.withPackages (
    ps: with ps; [
      pip
      ipykernel
      pytest
      nbmake
    ]
  );

  # A .venv next to the project, made and activated on entering the shell.
  venv = options.pythonVenv or false;

  tools = with pkgs; [
    # Toolchain: kernel, JupyterLab and Poetry-managed dependencies
    interpreter
    poetry
    uv

    # Language server
    basedpyright

    # Linters, type checking and notebook hygiene
    ruff
    mypy
    nbstripout

    # Security
    bandit

  ];
in
{
  description = "Jupyter development environment: JupyterLab, ruff, mypy and nbstripout";

  tools = tools ++ lib.optional venv python.pkgs.venvShellHook;

  semgrep = true;
  trivy = true;

  # More attributes for the shell itself.
  shell = lib.optionalAttrs venv {
    venvDir = ".venv";
  };

  lint = ''
    run ruff check .
    when pyproject.toml mypy .
  '';

  fmt = ''
    run ruff format .
    run_on '*.ipynb' nbstripout
  '';

  scan = ''
    # bandit reads a .bandit file by itself, and [tool.bandit] only when told where it is.
    if has tool.bandit pyproject.toml; then
      run bandit --quiet --recursive . --exclude ./.venv,./.direnv -c pyproject.toml
    else
      run bandit --quiet --recursive . --exclude ./.venv,./.direnv
    fi
  '';

  tests = {
    run = [
      ''
        # nbmake runs every notebook top to bottom.
        run_on '*.ipynb' python -m pytest --nbmake
      ''
    ];
  };
}
