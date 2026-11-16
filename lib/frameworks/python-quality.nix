# Standalone analysis never imports the application's framework. A configured
# framework-loading mypy plugin must run with the project's interpreter and
# existing checker/plugin versions, rather than Nix's unrelated Python graph.
extraRules: ''
  with_scripts 'python[0-9.]*' ruff check ${extraRules} .
  run vulture . --min-confidence 80 --exclude '.venv,.direnv,build,dist'
  if [ -e mypy.ini ] || [ -e .mypy.ini ] || has '[tool.mypy' pyproject.toml || has '[mypy]' setup.cfg; then
    run project_python -m mypy .
  else
    echo ":: skipping project mypy (no mypy configuration)"
  fi
''
