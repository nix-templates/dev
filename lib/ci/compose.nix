# The dev shell of a checkout that has no flake of its own.
#
# `ci` finds the checkout's languages and asks for this: the shell the same
# `mkProject` gives a flake that names those languages, with the nixpkgs that
# `ci` itself was built from.
{
  # The nixpkgs source tree.
  nixpkgs,
  system,
  # Names from lib/languages.
  languages,
}:
let
  lib = import (nixpkgs + "/lib");
  dev = import ../. { inherit lib; };

  # A language that needs something allowed in nixpkgs says so as the lines its
  # template writes into `import inputs.nixpkgs { ... }`. They are read here
  # the way they are read there.
  lines = lib.unique (
    lib.concatMap (
      name:
      let
        module = dev.languages.${name};
      in
      (
        if builtins.isFunction module then
          module {
            inherit lib;
            pkgs = throw "nix-templates/dev: nixpkgsConfig of '${name}' may not depend on pkgs";
            options = { };
          }
        else
          module
      ).nixpkgsConfig or [ ]
    ) (builtins.filter (name: dev.languages ? ${name}) languages)
  );
  settings = import (builtins.toFile "nixpkgs-settings.nix" ''
    { inputs }:
    {
      ${lib.concatStringsSep "\n  " lines}
    }
  '') { inputs.nixpkgs = { inherit lib; }; };

  pkgs = import nixpkgs {
    inherit system;
    config = settings.config or { };
    overlays = [ ];
  };

in
(dev.mkProject { inherit pkgs languages; }).devShell
