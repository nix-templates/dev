#!/usr/bin/env bash
# Run inside a template's dev shell, in a project fresh from that template.
#
# The five commands are there and come from the dev shell, and each of them
# runs: 0 (passed) and 1 (found something) both mean it ran, anything else
# means it could not. A tool that cannot start on this system mostly ends in 1
# as well, so its output is looked through for the lines that give that away.
#
# On macOS `security` is also the keychain tool, which programs call by that
# name. With arguments ours has to be that tool still.
#
# What happened is written to the file $RESULTS names, one `name=value` a line.
set -u

failed=0
log=$(mktemp)
could_not_start='command not found|cannot execute binary file|Bad CPU type in executable|Library not loaded|dyld\[|Exec format error|error while loading shared libraries|Illegal instruction|Segmentation fault'

note() {
  if [ -n "${RESULTS:-}" ]; then
    echo "$1=$2" >> "$RESULTS"
  fi
}

for command in quality "style --check" security architecture tests; do
  name=${command%% *}
  path=$(command -v "$name" || true)
  case "$path" in
    /nix/store/*) ;;
    "")
      echo "FAIL: the dev shell has no $name"
      note "$name" missing
      failed=1
      continue
      ;;
    *)
      echo "FAIL: $name is $path, which is not the dev shell's"
      note "$name" "not the dev shell's"
      failed=1
      continue
      ;;
  esac

  echo "::group::$command"
  code=0
  # shellcheck disable=SC2086 # the command and its one argument
  $command > "$log" 2>&1 < /dev/null || code=$?
  cat "$log"
  echo "::endgroup::"

  outcome="ran ($code)"
  if [ "$code" -gt 1 ]; then
    echo "FAIL: $command ended with $code"
    outcome="could not run ($code)"
    failed=1
  fi
  if grep -E -m 3 "$could_not_start" "$log"; then
    echo "FAIL: a tool of $command could not start on this system"
    outcome="a tool could not start ($code)"
    failed=1
  fi
  note "$name" "$outcome"
done

if [ "$(uname -s)" = Darwin ]; then
  keychain="as before"
  for arguments in "list-keychains" "find-identity -v" "help"; do
    # shellcheck disable=SC2086 # the subcommand and its arguments
    ours=$(security $arguments 2>&1 < /dev/null) && ours_code=0 || ours_code=$?
    # shellcheck disable=SC2086
    theirs=$(/usr/bin/security $arguments 2>&1 < /dev/null) && theirs_code=0 || theirs_code=$?
    if [ "$ours" != "$theirs" ] || [ "$ours_code" != "$theirs_code" ]; then
      echo "FAIL: \`security $arguments\` in the dev shell is not the keychain tool:"
      echo "  in the dev shell ($ours_code): $(head -n 3 <<< "$ours")"
      echo "  /usr/bin/security ($theirs_code): $(head -n 3 <<< "$theirs")"
      keychain="broken"
      failed=1
    fi
  done
  echo "security with arguments: the keychain tool, $keychain"
  note keychain "$keychain"
else
  note keychain "not macOS"
fi

rm -f "$log"
exit "$failed"
