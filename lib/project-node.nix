# Resolve only installed project executables, including declared workspaces.
{ pkgs }:
let
  readerPython = pkgs.python3.withPackages (ps: [ ps.pyyaml ]);
in
''
  export DVT_PROJECT_ROOT="$PWD"
  js_pm() {
    (cd "$DVT_PROJECT_ROOT" && ${readerPython}/bin/python3 -I -B ${./frameworks/version_guard.py} --node-manager)
  }
  project_yarn() {
    local binary
    if [ -n "''${DVT_PROJECT_YARN:-}" ]; then
      "$DVT_PROJECT_YARN" "$@"
    elif binary=$(cd "$DVT_PROJECT_ROOT" && ${readerPython}/bin/python3 -I -B ${./frameworks/version_guard.py} --yarn-path 2>/dev/null); then
      case "$binary" in
        *.cjs | *.js) node "$binary" "$@" ;;
        *) "$binary" "$@" ;;
      esac
    elif (cd "$DVT_PROJECT_ROOT" && ${readerPython}/bin/python3 -I -B ${./frameworks/version_guard.py} --node-pnp) >/dev/null 2>&1; then
      echo "Yarn PnP needs the project's Yarn executable; set DVT_PROJECT_YARN or configure yarnPath. No dependency was added." >&2
      return 127
    else
      yarn "$@"
    fi
  }
  js_require() {
    if (cd "$DVT_PROJECT_ROOT" && ${readerPython}/bin/python3 -I -B ${./frameworks/version_guard.py} --node-bin "$1") >/dev/null 2>&1; then return 0; fi
    if (cd "$DVT_PROJECT_ROOT" && ${readerPython}/bin/python3 -I -B ${./frameworks/version_guard.py} --node-pnp) >/dev/null 2>&1 && project_yarn bin "$1" >/dev/null 2>&1; then return 0; fi
    echo "Project tool $1 is missing; no dependency was added." >&2
    return 127
  }
  js_exec() {
    local tool="$1" executable
    shift
    if executable=$(cd "$DVT_PROJECT_ROOT" && ${readerPython}/bin/python3 -I -B ${./frameworks/version_guard.py} --node-bin "$tool" 2>/dev/null); then
      "$executable" "$@"
    elif (cd "$DVT_PROJECT_ROOT" && ${readerPython}/bin/python3 -I -B ${./frameworks/version_guard.py} --node-pnp) >/dev/null 2>&1; then
      project_yarn exec "$tool" "$@"
    else
      echo "Project tool $tool is missing; no dependency was added." >&2
      return 127
    fi
  }
''
