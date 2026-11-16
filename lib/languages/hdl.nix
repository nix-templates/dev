# Hardware description.
{
  pkgs,
  lib,
  ...
}:
{
  description = "Hardware description environment: Verible, svls, Verilator, GHDL and Yosys";

  tools =
    with pkgs;
    [
      # Simulation and synthesis
      verilator
      iverilog
      ghdl
      gtkwave

      # Language servers
      verible
      svls

      # Linter and formatter (both from Verible)
      verible

      # Tests: formal verification of *.sby tasks
      sby
    ]
    # Yosys builds against sv-lang, which nixpkgs marks broken on Darwin, so
    # macOS gets the rest of the environment rather than no shell at all.
    ++ lib.optional (!stdenv.hostPlatform.isDarwin) yosys;

  quality = ''
    run_on '*.sv' verible-verilog-lint
    run_on '*.v' verible-verilog-lint
    run_on '*.sv' verible-verilog-format --verify
  '';

  style = ''
    run_on '*.sv' verible-verilog-format --inplace
    run_on '*.v' verible-verilog-format --inplace
  '';

  tests = {
    run = [
      ''
        for_each '*.sby' sby -f
      ''
    ];
  };
}
