# Shared helpers. `run` keeps going after a failure so you see every problem in
# one pass; `run_on` skips a tool entirely when the project has no such files.
status=0

run() {
  echo ":: $*"
  "$@" || status=1
}

collect() {
  find . \( -name .git -o -name .direnv -o -name .venv -o -name node_modules -o -name target -o -name result -o -name build -o -name dist -o -name .build -o -name _build -o -name vendor -o -name .terraform -o -name .stack-work \) -prune -o -type f -name "$1" -print
}

run_on() {
  local pattern="$1"
  shift
  local files=()
  mapfile -t files < <(collect "$pattern")
  if [ "${#files[@]}" -eq 0 ]; then
    echo ":: skipping $1 (no $pattern files)"
    return
  fi
  run "$@" "${files[@]}"
}

for_each() {
  local pattern="$1"
  shift
  local files=()
  mapfile -t files < <(collect "$pattern")
  if [ "${#files[@]}" -eq 0 ]; then
    echo ":: skipping $1 (no $pattern files)"
    return
  fi
  local file
  for file in "${files[@]}"; do
    run "$@" "$file"
  done
}

if_have() {
  local bin="$1"
  shift
  if command -v "$bin" > /dev/null 2>&1; then
    run "$@"
  else
    echo ":: skipping $1 ($bin is not on PATH)"
  fi
}

when() {
  local guard="$1"
  shift
  if [ -e "$guard" ]; then
    run "$@"
  else
    echo ":: skipping $1 (no $guard here)"
  fi
}

when_any() {
  local pattern="$1"
  shift
  if [ -n "$(collect "$pattern" | head -n 1)" ]; then
    run "$@"
  else
    echo ":: skipping $1 (no $pattern files)"
  fi
}

# shell_scripts: every *.sh and *.bash file, and every file with no extension
# whose first line names sh, bash, dash or ksh.
shell_scripts() {
  collect '*.sh'
  collect '*.bash'
  local file
  while IFS= read -r file; do
    if head -n 1 -- "$file" 2> /dev/null | grep -qE '^#!.*[/ ](ba|da|k)?sh( |$)'; then
      echo "$file"
    fi
  done < <(find . \( -name .git -o -name .direnv -o -name .venv -o -name node_modules -o -name target -o -name result -o -name build -o -name dist -o -name .build -o -name _build -o -name vendor -o -name .terraform -o -name .stack-work \) -prune -o -type f ! -name '*.*' -print)
}

# on_shell_scripts command...: run the command on the project's shell scripts.
on_shell_scripts() {
  local files=()
  mapfile -t files < <(shell_scripts)
  if [ "${#files[@]}" -eq 0 ]; then
    echo ":: skipping $1 (no shell scripts)"
    return
  fi
  run "$@" "${files[@]}"
}

# has TEXT FILE...: true when one of the files exists and contains TEXT.
has() {
  local text="$1"
  shift
  grep -qsF -- "$text" "$@"
}

# when_has FILE TEXT command...: run the command when FILE contains TEXT.
when_has() {
  local file="$1" text="$2"
  shift 2
  if has "$text" "$file"; then
    run "$@"
  else
    echo ":: skipping $1 ($file does not mention $text)"
  fi
}

# found PATTERN...: true when the project has a file matching one of the patterns.
found() {
  local pattern
  for pattern in "$@"; do
    if [ -n "$(collect "$pattern" | head -n 1)" ]; then
      return 0
    fi
  done
  return 1
}

# The project's JavaScript package manager, told by its lockfile.
js_pm() {
  if [ -e pnpm-lock.yaml ]; then
    echo pnpm
  elif [ -e yarn.lock ]; then
    echo yarn
  elif [ -e bun.lock ] || [ -e bun.lockb ]; then
    echo bun
  else
    echo npm
  fi
}

# js_exec TOOL args...: run a tool the project installed for itself.
js_exec() {
  case "$(js_pm)" in
    pnpm) pnpm exec "$@" ;;
    yarn) yarn exec "$@" ;;
    bun) bunx "$@" ;;
    *) npx --no-install "$@" ;;
  esac
}
