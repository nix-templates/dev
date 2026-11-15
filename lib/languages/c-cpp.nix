# C and C++.
{ pkgs, lib, ... }:
{
  tools =
    with pkgs;
    [
      cmake
      ninja
      meson
      bear
      gtest
      lcov
      doxygen

      # clangd, clang-format and clang-tidy
      clang-tools
      cppcheck
      include-what-you-use
      codespell

      # Security: SAST
      flawfinder

      vcpkg
      vcpkg-tool
      lldb
    ]
    ++ lib.optionals stdenv.hostPlatform.isLinux [ gdb ];

  semgrep = true;

  # The shell needs a C compiler and its wrapper, so it is mkShell, not mkShellNoCC.
  needsCC = true;

  lint = ''
    run cppcheck --enable=warning,style,performance,portability --inline-suppr --suppress=missingIncludeSystem --error-exitcode=1 -i build -i .direnv .
    when compile_commands.json run-clang-tidy -p .
    run codespell --skip='./.git,./build,./.direnv'
  '';

  fmt = ''
    run_on '*.c' clang-format -i
    run_on '*.h' clang-format -i
    run_on '*.cpp' clang-format -i
    run_on '*.hpp' clang-format -i
  '';

  fmtCheck = ''
    run_on '*.c' clang-format --dry-run --Werror
    run_on '*.h' clang-format --dry-run --Werror
    run_on '*.cpp' clang-format --dry-run --Werror
    run_on '*.hpp' clang-format --dry-run --Werror
  '';

  scan = ''
    run flawfinder --quiet --error-level=4 .
  '';
}
