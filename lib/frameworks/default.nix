{ lib }:
lib.mapAttrs (
  name: metadata:
  metadata
  // {
    module =
      if (metadata.adapter or "") == "node" then
        import ./node.nix metadata
      else if (metadata.adapter or "") == "native" then
        import ./native.nix metadata
      else if (metadata.adapter or "") == "python" then
        import ./python.nix metadata
      else
        import (./. + "/${name}.nix");
  }
) (builtins.fromJSON (builtins.readFile ./registry.json))
