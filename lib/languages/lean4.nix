# Lean 4.
{ pkgs, ... }:
{
  description = "Lean 4 development environment; lake serves as the language server";

  tools = with pkgs; [
    # Toolchain: Lean ships its own language server, driven through lake
    lean4

  ];

  trivy = true;

  quality = ''
    when lakefile.toml lake build
    when lakefile.lean lake build
  '';

  style = ''
    run typos --write-changes .
  '';

  tests = {
    run = [
      ''
        if found lakefile.toml lakefile.lean; then
          if lake check-test > /dev/null 2>&1; then
            run lake test
          else
            echo ":: skipping lake test (the lakefile names no test driver)"
          fi
        fi
      ''
    ];
  };
}
