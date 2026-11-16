# Lua.
{ pkgs, ... }:
{
  description = "Lua development environment: lua-language-server, Selene, Luacheck and StyLua";

  tools = with pkgs; [
    # Toolchain: both the reference interpreter and LuaJIT
    lua5_4
    luajit

    # Language server
    lua-language-server

    # Linters
    selene
    lua54Packages.luacheck

    # Formatter
    stylua

    # Tests
    lua54Packages.busted
  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when selene.toml selene .
    when .luacheckrc luacheck .
    run stylua --check .
  '';

  style = ''
    run stylua .
  '';

  tests = {
    run = [
      ''
        if [ -e .busted ] || [ -d spec ]; then
          run busted
        fi
      ''
    ];
  };
}
