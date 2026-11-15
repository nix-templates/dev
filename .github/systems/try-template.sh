#!/usr/bin/env bash
# try-template.sh TEMPLATE [SYSTEM-NAME]
#
# A project fresh from a template of this checkout, on this machine: its dev
# shell is made, and the five commands run in it. The template takes the
# library from this checkout, not from what is published. The project gets the
# small sample of its language that the tests of `ci` use, so that the
# language's own tools have files to run on.
#
# A few samples are known to be clean (CLEAN in lib/ci/tests/samples.py). For
# those, every command has to end with 0.
#
# It ends with 0 when all of that worked, and with 1 when something did not.
# In a workflow it adds one row to the run's summary.
set -euo pipefail

template=$1
system=${2:-$(uname -s) $(uname -m)}
here=$(cd "$(dirname "$0")/../.." && pwd)

if [ ! -f "$here/$template/flake.nix" ]; then
  echo "there is no template $template" >&2
  exit 2
fi

work=$(mktemp -d)
results=$work.results
: > "$results"
cd "$work"
git init --quiet --initial-branch=main .
nix flake init --template "path:$here#$template"
python3 "$here/lib/ci/tests/samples.py" "$template" .
git add --all
clean=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import samples; print("true" if sys.argv[2] in samples.CLEAN else "false")' "$here/lib/ci/tests" "$template")

shell=made
code=0
RESULTS=$results EXPECT_CLEAN=$clean nix develop --override-input dev "path:$here" --command bash "$here/.github/systems/in-shell.sh" || code=$?
# No results at all: the dev shell itself could not be made or entered.
if [ ! -s "$results" ]; then
  shell="not made"
  echo "FAIL: the dev shell of $template could not be made here"
  code=1
fi

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "| template | system | dev shell | quality | style | security | architecture | tests | macOS keychain |"
    echo "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    printf '| %s | %s | %s |' "$template" "$system" "$shell"
    for name in quality style security architecture tests keychain; do
      printf ' %s |' "$(sed -n "s/^$name=//p" "$results" | head -n 1)"
    done
    echo
    echo
  } >> "$GITHUB_STEP_SUMMARY"
fi

rm -rf "$work" "$results"
exit "$code"
