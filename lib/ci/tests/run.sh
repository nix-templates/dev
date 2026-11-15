#!/usr/bin/env bash
# The built ci on a small checkout, with the commands mkProject writes for the
# two languages in ./languages. Only nix is a stand-in, because a build cannot
# ask Nix for a dev shell: it answers with the PATH in CI_TEST_PATH.
#
# Run by the flake's check `ci-run`, with ci on PATH.
set -euo pipefail

work=$(mktemp -d)
export XDG_CACHE_HOME="$work/cache"

mkdir "$work/bin"
cat > "$work/bin/nix" << END
#!/bin/sh
case " \$* " in
  *" print-dev-env "*) echo 'export PATH="$CI_TEST_PATH:\$PATH"' ;;
  *) echo "nix: unexpected: \$*" >&2; exit 64 ;;
esac
END
chmod +x "$work/bin/nix"
PATH="$work/bin:$PATH"

mkdir "$work/checkout"
cd "$work/checkout"
git init -q -b main
printf 'one\ntwo\n' > sample.words
git add -A
git -c user.name=test -c user.email=test@example.org commit -q -m start

failed=0

# expect CODE ci-arguments...: run ci, keep what it printed in $out and $err.
expect() {
  local wanted=$1 code=0
  shift
  ci "$@" > "$work/out" 2> "$work/err" || code=$?
  out=$(cat "$work/out")
  err=$(cat "$work/err")
  if [ "$code" -ne "$wanted" ]; then
    echo "FAIL: ci $* ended with $code, not $wanted"
    sed 's/^/    out: /' "$work/out"
    sed 's/^/    err: /' "$work/err"
    failed=1
  fi
}

# has TEXT WHERE WHAT: WHERE must have a line that is, or contains, TEXT.
has() {
  if ! grep -qF -- "$1" <<< "$2"; then
    echo "FAIL: $3 does not have: $1"
    sed 's/^/    /' <<< "$2"
    failed=1
  fi
}

lacks() {
  if grep -qF -- "$1" <<< "$2"; then
    echo "FAIL: $3 has: $1"
    failed=1
  fi
}

expect 0 quality
has "ci: quality in a dev shell made for no language by nix-templates/dev" "$(head -n 1 <<< "$err")" "the first line of quality"
has "ci: checked nothing (no-languages)" "$err" "quality"
has ":: test -s ./sample.words" "$out" "quality"
has ":: typos --format brief ." "$out" "quality"
lacks "checked nothing: quality for" "$out" "quality"

expect 0 style
has ":: sed -i" "$out" "style"
printf 'three  \n' >> sample.words
before=$(cat sample.words)
expect 1 style
has "style would change:" "$out" "style on a file with a space at the end of a line"
has "  sample.words" "$out" "style on a file with a space at the end of a line"
if [ "$(cat sample.words)" != "$before" ]; then
  echo "FAIL: style rewrote sample.words"
  failed=1
fi
git checkout -q sample.words

expect 0 security
has ":: gitleaks dir ." "$out" "security"

expect 0 tests
has ":: tests: run" "$out" "tests"
has ":: env" "$out" "tests"
has ":: checked nothing: tests for untested" "$out" "tests"
lacks "checked nothing: tests for tested" "$out" "tests"
has "ci: checked nothing (language): tests ran nothing for untested" "$err" "tests"
# Nothing of ci's own reaches the command.
lacks "PYTHONPATH=" "$out" "the environment of tests"
lacks "DEV_CI" "$out" "the environment of tests"
expect 1 --strict=language tests
has "ci: failing: --strict was given for language" "$err" "tests with --strict"
expect 2 tests --no-such-mode
has "tests: there is no 'no-such-mode' here" "$err" "tests with a mode it does not have"

expect 1 architecture
has "ci: architecture: there is no architecture.toml in this checkout" "$err" "architecture"
printf '[[layer]]\nname = "all"\npaths = ["."]\n' > architecture.toml
git add -A
expect 0 architecture
has "architecture: ok (" "$out" "architecture"
expect 0 architecture --since HEAD
has "ci: checked nothing (no-comparison): HEAD has no architecture.toml, so --since compared nothing" "$err" "architecture --since"

# The names four of the commands had before are gone: ci does not take them,
# and the dev shell has no command under them.
expect 2 lint
has "ci: there is no command lint. It is called quality now" "$err" "ci lint"
for before in lint fmt scan layers; do
  if PATH="$CI_TEST_PATH" command -v "$before" > /dev/null; then
    echo "FAIL: the dev shell still has $before"
    failed=1
  fi
done
for now in quality style security architecture tests; do
  if ! PATH="$CI_TEST_PATH" command -v "$now" > /dev/null; then
    echo "FAIL: the dev shell has no $now"
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  exit 1
fi
echo "ci-run: every command ran as it should"
