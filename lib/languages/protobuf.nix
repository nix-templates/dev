# Protobuf.
{ pkgs, ... }:
{
  description = "Protobuf environment: buf for LSP, lint, format and breaking-change detection";

  tools = with pkgs; [
    # Toolchain: protoc, buf and a gRPC client for poking at servers
    protobuf
    buf
    grpcurl

    # Linters
    protolint

  ];

  trivy = true;

  quality = ''
    when buf.yaml buf lint
    when_any '*.proto' protolint lint .
  '';

  style = ''
    when buf.yaml buf format --write
    when_any '*.proto' protolint lint --fix .
  '';

  security = ''
    when buf.yaml buf breaking --against .git#branch=main
  '';

  architecture = [
    ''
      # Breaking changes against the main branch, by the rules under `breaking:` in buf.yaml.
      buf_breaking() {
        if git rev-parse --verify --quiet main > /dev/null 2>&1; then
          buf breaking --against '.git#branch=main'
        else
          echo ":: skipping buf breaking (no main branch to compare with)"
        fi
      }
      when buf.yaml buf_breaking
    ''
  ];
}
