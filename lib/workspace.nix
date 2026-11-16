# Components run in distinct process environments. The shared shell contains
# the five dispatchers; each component also exposes its own isolated dev shell.
{ lib, mkProject }:
{
  pkgs,
  components,
  toolPkgs ? pkgs,
}:
let
  projects = lib.mapAttrs (
    _: component:
    mkProject (
      {
        inherit pkgs toolPkgs;
      }
      // builtins.removeAttrs component [
        "root"
        "enabledCommands"
      ]
    )
  ) components;
  names = [
    "quality"
    "style"
    "security"
    "architecture"
    "tests"
  ];
  commands = lib.genAttrs names (
    name:
    pkgs.writeShellApplication {
      inherit name;
      runtimeInputs = [ pkgs.git ];
      text = ''
        # Component commands use the shared `run` protocol: echo ":: $*"
        workspace_root="$PWD"
        status=0
        ran=0
        export DVT_WORKSPACE_ROOT="$workspace_root"
        ${lib.concatStrings (
          lib.mapAttrsToList (
            key: component:
            lib.optionalString (lib.elem name (component.enabledCommands or names)) ''
              ran=$((ran + 1))
              echo ${lib.escapeShellArg ":: component ${key}: ${name}"}
              if ! (cd "$workspace_root"/${lib.escapeShellArg component.root} && ${
                projects.${key}.commands.${name}
              }/bin/${name} "$@"); then status=1; fi
            ''
          ) components
        )}
        if [ "$ran" -eq 0 ]; then echo "${name}: no configured check was discovered" >&2; exit 2; fi
        exit "$status"
      '';
    }
  );
in
{
  inherit commands projects;
  devShell = pkgs.mkShellNoCC { packages = builtins.attrValues commands; };
  devShells = {
    default = pkgs.mkShellNoCC { packages = builtins.attrValues commands; };
  }
  // lib.mapAttrs' (name: project: lib.nameValuePair ("component-" + name) project.devShell) projects;
}
