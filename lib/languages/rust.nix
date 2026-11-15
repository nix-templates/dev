# Rust. `rustToolchain` is the project's own pinned toolchain (one derivation
# with cargo, rustc, clippy and rustfmt), so clippy runs on the compiler the
# project builds with. Without it, the four come from the project's nixpkgs.
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
  tools =
    toolchain
    ++ (with pkgs; [
      cargo-edit
      cargo-watch
      cargo-nextest
      bacon

      # Language server
      rust-analyzer

      # Linters and dependency hygiene
      cargo-deny
      cargo-machete
      cargo-outdated

      # Formatters (taplo covers Cargo.toml)
      taplo

      # Security: advisory database
      cargo-audit

      # Native build dependencies most crates end up needing
      openssl
      pkg-config
    ]);

  semgrep = true;

  env = lib.optionalAttrs (pinned == null) {
    RUST_SRC_PATH = "${pkgs.rustPlatform.rustLibSrc}";
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

  fmtCheck = ''
    when Cargo.toml cargo fmt --all -- --check
    when Cargo.toml taplo fmt --check
  '';

  scan = ''
    when Cargo.lock cargo audit
    when deny.toml cargo deny check
  '';
}
