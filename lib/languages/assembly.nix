# Assembly.
{
  pkgs,
  lib,
  ...
}:
let
  tools = with pkgs; [
    # Assemblers and the GNU binary utilities
    nasm
    yasm
    binutils

    # Language server
    asm-lsp

    # Reverse engineering and disassembly
    radare2

    # Debugger
    lldb

  ];

  # Tools that only exist, or only make sense, on one platform.
  platformTools =
    with pkgs;
    lib.optionals stdenv.hostPlatform.isLinux [
      gdb
    ];
in
{
  description = "Assembly development environment: asm-lsp, NASM, YASM and the GNU binutils";

  tools = tools ++ platformTools;

  # The shell needs a C compiler and its wrapper.
  needsCC = true;

  lint = ''
    for_each '*.asm' nasm -f elf64 -o /dev/null
  '';

  fmt = ''
    run typos --write-changes .
  '';
}
