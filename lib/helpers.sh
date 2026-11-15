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
