# Erlang.
{ pkgs, ... }:
{
  description = "Erlang development environment: the Erlang Language Platform (elp), rebar3 and erlfmt";

  tools = with pkgs; [
    # Toolchain
    erlang
    rebar3

    # Language server and static analyser (WhatsApp's elp)
    erlang-language-platform

    # Formatter
    erlfmt

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when rebar.config rebar3 dialyzer
    run_on '*.erl' erlfmt --check
  '';

  style = ''
    run_on '*.erl' erlfmt --write
  '';

  architecture = [
    ''
      when rebar.config rebar3 xref
    ''
  ];

  tests = {
    run = [
      ''
        when rebar.config rebar3 eunit
      ''
      ''
        when_any '*_SUITE.erl' rebar3 ct
      ''
    ];
    coverage = [
      ''
        when rebar.config rebar3 "do" eunit -c, cover -v
      ''
    ];
  };
}
