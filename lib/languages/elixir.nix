# Elixir.
{
  pkgs,
  lib,
  ...
}:
let
  tools = with pkgs; [
    # Toolchain: Elixir brings OTP, mix, hex and rebar3 with it
    elixir
    git

    # Language server
    elixir-ls

    # Node.js, for Phoenix asset pipelines
    nodejs

  ];

  # Tools that only exist, or only make sense, on one platform.
  platformTools =
    with pkgs;
    lib.optionals stdenv.hostPlatform.isLinux [
      inotify-tools
      libnotify
      gigalixir
    ]
    ++ lib.optionals stdenv.hostPlatform.isDarwin [
      terminal-notifier
    ];
in
{
  description = "Elixir development environment: ElixirLS plus mix format and mix credo";

  tools = tools ++ platformTools;

  semgrep = true;
  trivy = true;

  lint = ''
    when mix.exs mix compile --warnings-as-errors
    when mix.exs mix format --check-formatted
  '';

  fmt = ''
    when mix.exs mix format
  '';

  arch = [
    ''
      when mix.exs mix xref graph --format cycles --label compile-connected --fail-above 0
    ''
    ''
      when mix.lock mix deps.unlock --check-unused
    ''
  ];

  tests = {
    run = [
      ''
        when mix.exs mix test
      ''
    ];
    coverage = [
      ''
        when mix.exs mix test --cover
      ''
    ];
  };
}
