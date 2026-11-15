# Embedded.
{
  pkgs,
  lib,
  ...
}:
let
  tools = with pkgs; [
    # Embedded toolchain and build systems
    platformio
    cmake
    ninja
    bear

    # clangd, clang-tidy and clang-format
    clang-tools

    # Linters and tests
    cppcheck
    codespell
    gtest
    lcov

    # Security
    flawfinder

  ];

  # Tools that only exist, or only make sense, on one platform.
  platformTools =
    with pkgs;
    lib.optionals stdenv.hostPlatform.isLinux [
      gdb
    ];
in
{
  description = "Embedded environment: PlatformIO, clangd, clang-tidy, cppcheck and flawfinder";

  # A PlatformIO project has platformio.ini, and is then not also read as plain C and C++.
  marks = [
    "platformio.ini"
  ];
  insteadOf = [
    "c-cpp"
  ];

  tools = tools ++ platformTools;

  semgrep = true;

  # The shell needs a C compiler and its wrapper.
  needsCC = true;

  shellHook = ''
    # Keep PlatformIO's toolchains and caches inside the project instead of $HOME.
    export PLATFORMIO_CORE_DIR=$PWD/.platformio
  '';

  lint = ''
    run cppcheck --enable=warning,style,performance,portability --inline-suppr --suppress=missingIncludeSystem --error-exitcode=1 -i .pio -i .direnv .
    when compile_commands.json run-clang-tidy -p .
    run codespell --skip='./.git,./.pio,./.platformio,./.direnv'
  '';

  fmt = ''
    run_on '*.c' clang-format -i
    run_on '*.h' clang-format -i
    run_on '*.cpp' clang-format -i
  '';

  scan = ''
    run flawfinder --quiet --error-level=4 .
  '';

  tests = {
    run = [
      ''
        when_has platformio.ini env:native pio test -e native
      ''
    ];
  };
}
