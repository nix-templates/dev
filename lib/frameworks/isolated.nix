# Each tool owns its interpreter and plugins in its own derivation. Do not
# combine plugin dependencies with the project's interpreter or global PATH.
{ pkgs }:
name: package: binary:
pkgs.writeShellApplication {
  name = "dvt-${name}";
  text = ''
    exec env -u PYTHONPATH -u PYTHONHOME PYTHONNOUSERSITE=1 ${package}/bin/${binary} "$@"
  '';
}
