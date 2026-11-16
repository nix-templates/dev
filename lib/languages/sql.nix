# SQL.
{ pkgs, ... }:
{
  description = "SQL environment: sqls language server, SQLFluff, sqruff and pg_format";

  # SQL files.
  marks = [
    "*.sql"
  ];

  tools = with pkgs; [
    # Engines and clients
    postgresql
    sqlite
    pgcli
    usql

    # Language server
    sqls

    # Linters (sqruff is the fast Rust reimplementation of SQLFluff)
    sqlfluff
    sqruff

    # Formatter
    pgformatter

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when .sqlfluff sqlfluff lint .
    when .sqruff sqruff lint .
  '';

  style = ''
    for_each '*.sql' pg_format --inplace
  '';
}
