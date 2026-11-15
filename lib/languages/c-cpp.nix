# C/C++.
{
  pkgs,
  lib,
  ...
}:
let
  tools = with pkgs; [
    # Build systems and test/coverage tooling
    cmake
    ninja
    meson
    bear
    gtest
    lcov
    doxygen

    # clangd, clang-tidy and clang-format all come from clang-tools
    clang-tools

    # Linters and static analysis
    cppcheck
    include-what-you-use
    codespell

    # Security: C-specific SAST plus generic scanning
    flawfinder

    # Package management and debugging
    vcpkg
    vcpkg-tool
    lldb

    # Tests: coverage reports from gcov data
    gcovr
  ];

  # Tools that only exist, or only make sense, on one platform.
  platformTools =
    with pkgs;
    lib.optionals stdenv.hostPlatform.isLinux [
      gdb
    ];
in
{
  description = "C/C++ development environment: clangd, clang-tidy, cppcheck, flawfinder and clang-format";

  tools = tools ++ platformTools;

  semgrep = true;
  trivy = true;

  # The shell needs a C compiler and its wrapper.
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

  scan = ''
    run flawfinder --quiet --error-level=4 .
  '';

  tests = {
    run = [
      ''
        cmake_tests() {
          cmake -S . -B build && cmake --build build && ctest --test-dir build --output-on-failure
        }
        when CMakeLists.txt cmake_tests
      ''
      ''
        meson_tests() {
          if [ ! -d build ]; then
            meson setup build
          fi
          meson test -C build --print-errorlogs
        }
        when meson.build meson_tests
      ''
    ];
  };
}
