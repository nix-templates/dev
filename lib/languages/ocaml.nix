# OCaml.
{ pkgs, ... }:
{
  description = "OCaml development environment: ocaml-lsp, Dune, ocamlformat and odoc";

  tools = with pkgs; [
    # Toolchain
    ocaml
    opam
    ocamlPackages.dune_3
    ocamlPackages.utop
    ocamlPackages.odoc

    # Language server
    ocamlPackages.ocaml-lsp

    # Formatter
    ocamlformat

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when dune-project dune build @check
    when .ocamlformat dune build @fmt
  '';

  style = ''
    when .ocamlformat dune build @fmt --auto-promote
  '';

  tests = {
    run = [
      ''
        when dune-project dune runtest
      ''
    ];
    coverage = [
      ''
        # bisect_ppx comes from the project's own opam switch.
        dune_coverage() {
          dune runtest --instrument-with bisect_ppx --force && bisect-ppx-report summary
        }
        when dune-project dune_coverage
      ''
    ];
  };
}
