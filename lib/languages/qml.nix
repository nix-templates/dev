# QML (Qt Quick). qmllint needs the project's QML import paths to resolve
# modules; without them it still catches syntax errors.
{ pkgs, ... }:
{
  # qmllint, qmlformat and the qmlls language server
  tools = [ pkgs.qt6.qtdeclarative ];

  lint = ''
    run_on '*.qml' qmllint
  '';

  fmt = ''
    run_on '*.qml' qmlformat --inplace
  '';

  # qmlformat has no check mode, so compare what it would write with the file.
  fmtCheck = ''
    qml_formatted() {
      qmlformat "$1" | diff -q - "$1" > /dev/null || {
        echo "$1 is not formatted"
        return 1
      }
    }
    for_each '*.qml' qml_formatted
  '';
}
