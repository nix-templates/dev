# Go.
{ pkgs, ... }:
{
  description = "Go development environment: gopls, golangci-lint, gofumpt, gosec and govulncheck";

  tools = with pkgs; [
    # Toolchain: compiler, goimports/godoc, test runner and debugger
    go
    gotools
    gotestsum
    delve

    # Language server
    gopls

    # Linters and static analysis (golangci-lint bundles ~100 linters)
    golangci-lint
    go-tools

    # Formatter (stricter superset of gofmt)
    gofumpt

    # Security: SAST, known-vulnerability and dependency scanning
    gosec
    govulncheck

    # Architecture: layers and allowed imports from .go-arch-lint.yml
    go-arch-lint
  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when go.mod golangci-lint run ./...
    when go.mod go vet ./...
    when go.mod staticcheck ./...
  '';

  style = ''
    run gofumpt -l -w .
  '';

  security = ''
    when go.mod gosec -quiet ./...
    when go.mod govulncheck ./...
  '';

  architecture = [
    ''
      when .go-arch-lint.yml go-arch-lint check
    ''
  ];

  tests = {
    run = [
      ''
        when go.mod gotestsum --format pkgname -- ./...
      ''
    ];
    coverage = [
      ''
        go_coverage() {
          go test -coverprofile=cover.out ./... && go tool cover -func=cover.out
        }
        when go.mod go_coverage
      ''
    ];
    bench = [
      ''
        when go.mod go test -run '^$' -bench . -benchmem ./...
      ''
    ];
  };
}
