# Python.
{
  pkgs,
  lib,
  options,
  ...
}:
let
  # `python` in mkProject moves the whole environment to another Python.
  python = options.python or pkgs.python313;

  # The interpreter with the test tools in it, so that `python -m pytest` finds
  # them. Separate packages on PATH would not see each other.
  interpreter = python.withPackages (
    ps: with ps; [
      pip
      pytest
      pytest-cov
      hypothesis
    ]
  );

  # A .venv next to the project, made and activated on entering the shell.
  venv = options.pythonVenv or false;

  tools = with pkgs; [
    # Toolchain: interpreter, virtualenv hook and the uv package manager
    interpreter
    uv

    # Language servers (ruff also ships one, for lint diagnostics)
    basedpyright

    # Linters, type checkers and dead-code detection
    ruff
    mypy
    python.pkgs.vulture

    # Security: SAST for Python and dependency/secret scanning
    bandit

    # Tests: mutation testing (pytest, pytest-cov and hypothesis are in the interpreter)
    mutmut

    # Architecture: unused, missing and misplaced dependencies
    deptry
  ];
in
{
  description = "Python development environment: basedpyright, ruff, mypy and bandit";

  tools = tools ++ lib.optional venv python.pkgs.venvShellHook;

  semgrep = true;
  trivy = true;

  # More attributes for the shell itself.
  shell = lib.optionalAttrs venv {
    venvDir = ".venv";
    postShellHook = ''
      venvVersionWarn() {
        local venvVersion
        venvVersion="$("$venvDir/bin/python" -c 'import platform; print(platform.python_version())')"

        [[ "$venvVersion" == "${python.version}" ]] && return

        cat <<EOF
      Warning: Python version mismatch: [$venvVersion (venv)] != [${python.version}]
      Delete '$venvDir' and reload to rebuild for it to be rebuilt for ${python.version}
      EOF
      }

      venvVersionWarn
    '';
  };

  lint = ''
    run ruff check .
    when pyproject.toml mypy .
    run vulture . --min-confidence 80 --exclude '.venv,.direnv,build,dist'
  '';

  fmt = ''
    run ruff check --select I --fix .
    run ruff format .
  '';

  scan = ''
    run bandit --quiet --recursive . --exclude ./.venv,./.direnv
  '';

  layers = [
    ''
      when_has pyproject.toml tool.deptry deptry .
    ''
    ''
      # import-linter is not in nixpkgs: it runs when the project's own environment has it.
      if [ -e .importlinter ] || has tool.importlinter pyproject.toml; then
        if_have lint-imports lint-imports
      fi
    ''
  ];

  tests = {
    run = [
      ''
        if [ -d tests ] || [ -d test ] || [ -e pytest.ini ] || has tool.pytest pyproject.toml; then
          run python -m pytest -q
        fi
      ''
    ];
    coverage = [
      ''
        if [ -d tests ] || [ -d test ] || [ -e pytest.ini ] || has tool.pytest pyproject.toml; then
          run python -m pytest --cov --cov-report=term-missing
        fi
      ''
    ];
    mutation = [
      ''
        when_has pyproject.toml tool.mutmut mutmut run
      ''
    ];
  };
}
