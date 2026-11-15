# Rust.
#
# `rustToolchain` in mkProject is the project's own pinned toolchain: one
# derivation with cargo, rustc, clippy and rustfmt, so that clippy runs on the
# compiler the project builds with. Without it the four come from pkgs.
{
  pkgs,
  lib,
  options,
  ...
}:
let
  pinned = options.rustToolchain or null;
  toolchain =
    if pinned != null then
      lib.toList pinned
    else
      with pkgs;
      [
        cargo
        rustc
        clippy
        rustfmt
      ];
in
{
  description = "Rust development environment: rust-analyzer, clippy, rustfmt, cargo-audit and cargo-deny";

  tools =
    toolchain
    ++ (with pkgs; [
      cargo-edit
      cargo-watch
      cargo-nextest
      bacon

      # Language server
      rust-analyzer

      # Linters and dependency hygiene (clippy comes with the toolchain)
      cargo-deny
      cargo-machete
      cargo-outdated

      # Formatters (rustfmt comes with the toolchain; taplo covers Cargo.toml)
      taplo

      # Security: advisory database
      cargo-audit

      # Tests: coverage and mutation testing
      cargo-llvm-cov
      cargo-mutants

      # Native build dependencies most crates end up needing
      openssl
      pkg-config
    ]);

  semgrep = true;
  trivy = true;

  # cargo links build scripts, tests and binaries with `cc`.
  needsCC = true;

  # cargo-llvm-cov needs the llvm tools of the compiler's own LLVM. A pinned
  # toolchain brings them as its `llvm-tools` component.
  env = lib.optionalAttrs (pinned == null) {
    RUST_SRC_PATH = "${pkgs.rustPlatform.rustLibSrc}";
    LLVM_COV = "${pkgs.rustc.llvmPackages.llvm}/bin/llvm-cov";
    LLVM_PROFDATA = "${pkgs.rustc.llvmPackages.llvm}/bin/llvm-profdata";
  };

  lint = ''
    when Cargo.toml cargo clippy --all-targets --all-features -- --deny warnings
    when Cargo.toml cargo machete
    when Cargo.toml taplo lint
  '';

  fmt = ''
    when Cargo.toml cargo fmt --all
    when Cargo.toml taplo fmt
  '';

  scan = ''
    when Cargo.lock cargo audit
    when deny.toml cargo deny check
  '';

  layers = [
    ''
      # Banned crates, and which crates may pull one in (`wrappers`), from deny.toml.
      when deny.toml cargo deny check bans
    ''
  ];

  tests = {
    run = [
      ''
        when Cargo.toml cargo nextest run --all-features --no-tests=warn
        # nextest does not run doctests. Only a library has them: for a package
        # of binaries alone, cargo calls `test --doc` an error.
        if [ -e Cargo.toml ] && cargo metadata --no-deps --format-version 1 2> /dev/null | grep -qE '"kind":\["(lib|rlib|dylib|cdylib|staticlib|proc-macro)"'; then
          run cargo test --doc --all-features
        else
          echo ":: skipping cargo test --doc (no library here)"
        fi
      ''
    ];
    coverage = [
      ''
        when Cargo.toml cargo llvm-cov --all-features
      ''
    ];
    mutation = [
      ''
        when Cargo.toml cargo mutants
      ''
    ];
    bench = [
      ''
        when Cargo.toml cargo bench
      ''
    ];
  };
}
