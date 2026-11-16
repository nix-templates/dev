{
  pkgs,
  lib,
  dev,
}:
let
  component = name: {
    root = name;
    languages = [
      {
        env.DVT_COMPONENT = name;
        tools = [
          (pkgs.writeShellScriptBin "component-probe" ''
            set -e
            test "$DVT_COMPONENT" = ${name}
            test "$(basename "$PWD")" = ${name}
            echo ${name} >> "$DVT_WORKSPACE_ROOT/results"
            test "''${DVT_FAIL_COMPONENT:-}" != ${name}
          '')
        ];
      }
    ];
    configured = lib.genAttrs [ "quality" "style" "security" "architecture" "tests" ] (_: [
      {
        runner = "environment";
        argv = [ "component-probe" ];
      }
    ]);
  };
  workspace = dev.mkWorkspace {
    inherit pkgs;
    components = {
      left = component "left";
      right = component "right";
    };
  };
  empty = dev.mkWorkspace {
    inherit pkgs;
    components.left = (component "left") // {
      enabledCommands = [ "quality" ];
    };
  };
in
pkgs.runCommand "workspace-checks"
  {
    nativeBuildInputs = [
      pkgs.coreutils
      pkgs.gnugrep
    ];
  }
  ''
    mkdir left right
    ${lib.concatMapStrings
      (category: ''
        rm -f results
        ${workspace.commands.${category}}/bin/${category} > ${category}.log 2>&1 || { cat ${category}.log; exit 1; }
        test "$(cat results)" = "$(printf 'left\nright')"
        rm results
        if DVT_FAIL_COMPONENT=left ${workspace.commands.${category}}/bin/${category} > failure.log 2>&1; then echo 'component failure was lost'; exit 1; fi
        # A failed component must not hide results from the other component.
        test "$(cat results)" = "$(printf 'left\nright')"
      '')
      [
        "quality"
        "style"
        "security"
        "architecture"
        "tests"
      ]
    }
    code=0
    ${empty.commands.architecture}/bin/architecture > absent.log 2>&1 || code=$?
    test "$code" -eq 2
    grep 'no configured check was discovered' absent.log
    touch $out
  ''
