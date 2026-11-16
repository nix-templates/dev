# Test fixtures only. These pinned wheels never enter a generated project's shell.
{ pkgs }:
let
  pins = builtins.fromJSON (builtins.readFile ./packages.json);
  ps = pkgs.python312Packages;
  wheel =
    key: dependencies:
    let
      pin = pins.${key};
    in
    ps.buildPythonPackage {
      inherit (pin) pname version;
      format = "wheel";
      src = pkgs.fetchurl { inherit (pin) url sha256; };
      inherit dependencies;
      doCheck = false;
    };
  django =
    version:
    wheel "django-${version}" [
      ps.asgiref
      ps.sqlparse
    ];
  flask =
    version:
    wheel "flask-${version}" [
      ps.werkzeug
      ps.jinja2
      ps.itsdangerous
      ps.click
      ps.blinker
    ];
  starlette = wheel "starlette-0.46.2" [ ps.anyio ];
  fastapi = wheel "fastapi-0.115.14" [
    starlette
    ps.pydantic
    ps.typing-extensions
  ];
in
{
  django = {
    "4.2" = django "4.2.27";
    "5.2" = django "5.2.9";
    "6.0" = django "6.0";
  };
  flask = {
    "3.0" = flask "3.0.3";
    "3.1" = flask "3.1.2";
  };
  fastapi."0.115" = fastapi;
}
