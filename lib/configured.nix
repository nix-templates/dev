# Commands discovered from existing project configuration. Each argv is data;
# discovery never evaluates the application's configuration or shell scripts.
{
  pkgs,
  lib,
  configured,
  options,
}:
let
  render =
    spec:
    let
      args = lib.escapeShellArgs spec.argv;
      runners = {
        node = "dvt_node";
        python = "project_python ${./dvt/project-python-tool.py}";
        php = "dvt_php";
        ruby = "dvt_ruby";
        script = "dvt_script";
        composer = "dvt_composer";
        gradle = "./gradlew --offline --no-daemon";
        maven = "./mvnw --offline --batch-mode";
        environment = "dvt_environment";
      };
      invocation = "${runners.${spec.runner}} ${args}";
    in
    ''
      ${lib.concatMapStrings (binary: "dvt_node_require ${lib.escapeShellArg binary}\n") (
        spec.requires or [ ]
      )}
      run ${invocation}
    '';
  blocks = category: lib.concatMapStrings render (configured.${category} or [ ]);
in
{
  tools = lib.unique (
    map (name: pkgs.${name}) (
      lib.filter (name: builtins.hasAttr name pkgs) (
        map (spec: builtins.head spec.argv) (
          lib.filter (spec: spec.runner == "environment") (lib.concatLists (builtins.attrValues configured))
        )
      )
    )
  );
  preflight = (import ./project-node.nix { inherit pkgs; }) + ''
    export CI=true BUNDLE_FROZEN=true
    dvt_node_require() { js_require "$@"; }
    dvt_node() { js_exec "$@"; }
    dvt_script() {
      if [ "$(js_pm)" = yarn ]; then project_yarn run "$@";
      else "$(js_pm)" run "$@"; fi
    }
    dvt_php() { "''${DVT_PROJECT_PHP:-php}" "$@"; }
    dvt_ruby() { "''${DVT_PROJECT_RUBY:-ruby}" -S bundle exec "$@"; }
    dvt_composer() { "''${DVT_PROJECT_COMPOSER:-composer}" --no-interaction run-script "$@"; }
    dvt_environment() {
      local tool="$1"
      shift
      for directory in .venv/bin .tools/bin .bin bin; do
        if [ -x "$directory/$tool" ]; then "$directory/$tool" "$@"; return $?; fi
      done
      "$tool" "$@"
    }
  '';
  quality = blocks "quality";
  style = blocks "style";
  security = blocks "security";
  architecture = lib.optional (configured ? architecture) (blocks "architecture");
  tests = lib.optionalAttrs (configured ? tests) { run = [ (blocks "tests") ]; };
}
