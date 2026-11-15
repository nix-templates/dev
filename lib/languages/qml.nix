# QML (Qt Quick).
{ pkgs, ... }:
{
  description = "QML development environment: qmllint, qmlformat and the qmlls language server";

  # qmllint, qmlformat and qmlls. qmllint needs the project's QML import paths
  # to resolve modules; without them it still catches syntax errors.
  tools = [ pkgs.qt6.qtdeclarative ];

  lint = ''
    run_on '*.qml' qmllint
  '';

  fmt = ''
    run_on '*.qml' qmlformat --inplace
  '';
}
