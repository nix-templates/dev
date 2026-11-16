{ pkgs }:
let
  sources = builtins.fromJSON (builtins.readFile ./import-linter.json);
  ps = pkgs.python312Packages;
  wheel =
    name:
    ps.buildPythonPackage {
      pname = name;
      inherit (sources.${name}) version;
      format = "wheel";
      src = pkgs.fetchurl sources.${name}.wheels.${pkgs.stdenv.hostPlatform.system};
      propagatedBuildInputs =
        if name == "import-linter" then
          [
            ps.click
            ps.rich
            (wheel "grimp")
          ]
        else
          [ ];
      nativeBuildInputs = pkgs.lib.optionals pkgs.stdenv.hostPlatform.isLinux [ pkgs.autoPatchelfHook ];
      buildInputs = pkgs.lib.optionals pkgs.stdenv.hostPlatform.isLinux [ pkgs.stdenv.cc.cc.lib ];
      doCheck = false;
    };
in
pkgs.python312.withPackages (_: [ (wheel "import-linter") ])
