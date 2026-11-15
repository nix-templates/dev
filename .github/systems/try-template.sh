#!/usr/bin/env bash
# try-template.sh TEMPLATE [SYSTEM-NAME]
#
# A project fresh from a template of this checkout, on this machine: its dev
# shell is made, and the five commands run in it. The template takes the
# library from this checkout, not from what is published.
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
git add --all

shell=made
code=0
RESULTS=$results nix develop --override-input dev "path:$here" --command bash "$here/.github/systems/in-shell.sh" || code=$?
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
