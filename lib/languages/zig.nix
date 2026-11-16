# Zig.
{ pkgs, ... }:
{
  description = "Zig development environment: zls, zig fmt and the LLDB debugger";

  tools = with pkgs; [
    # Toolchain: zig fmt and zig build test are built in
    zig

    # Language server
    zls

    # Debugger
    lldb

  ];

  trivy = true;

  quality = ''
    run zig fmt --check .
  '';

  style = ''
    run zig fmt .
  '';

  tests = {
    run = [
      ''
        when build.zig zig build test --summary all
      ''
    ];
  };
}
