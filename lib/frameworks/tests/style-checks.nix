# Exercise the source-copy comparison with a real formatter and its cache.
{ pkgs, dev }:
let
  pythonProject = dev.mkProject {
    inherit pkgs;
    languages = [ "python" ];
  };
  style = pkgs.writeShellApplication {
    name = "style";
    text = pythonProject.texts.style;
    runtimeInputs = with pkgs; [
      coreutils
      git
      gnugrep
      rsync
      ruff
    ];
    excludeShellChecks = [ "SC2329" ];
  };
  sourceChange =
    action:
    pkgs.writeShellApplication {
      name = "style-${action}";
      text =
        (dev.mkProject {
          inherit pkgs;
          languages = [
            { style = if action == "create" then "run cp app.py generated.py\n" else "run rm app.py\n"; }
          ];
        }).texts.style;
      runtimeInputs = with pkgs; [
        coreutils
        git
        gnugrep
        rsync
      ];
      excludeShellChecks = [ "SC2329" ];
    };
in
pkgs.runCommand "style-check-regressions"
  {
    nativeBuildInputs = with pkgs; [
      coreutils
      git
      gnugrep
      ruff
    ];
  }
  ''
    mkdir checkout
    cd checkout
    git init --quiet
    echo 'value = 1' > app.py
    git add app.py
    # quality normally warms this cache before style runs in the systems workflow.
    ruff check .
    test -d .ruff_cache
    ${style}/bin/style --check > "$TMPDIR/clean.log" 2>&1 || { cat "$TMPDIR/clean.log"; exit 1; }
    rm -rf .ruff_cache
    ${style}/bin/style --check > "$TMPDIR/cold.log" 2>&1 || { cat "$TMPDIR/cold.log"; exit 1; }
    test ! -e .ruff_cache
    echo 'value=1' > app.py
    if ${style}/bin/style --check > "$TMPDIR/changed.log" 2>&1; then echo 'unformatted source passed'; exit 1; fi
    grep '  app.py' "$TMPDIR/changed.log"
    test "$(cat app.py)" = 'value=1'
    echo 'value = 1' > app.py
    if ${sourceChange "create"}/bin/style-create --check > "$TMPDIR/created.log" 2>&1; then echo 'new source file was ignored'; exit 1; fi
    grep 'generated.py' "$TMPDIR/created.log"
    test ! -e generated.py
    if ${sourceChange "delete"}/bin/style-delete --check > "$TMPDIR/deleted.log" 2>&1; then echo 'source deletion was ignored'; exit 1; fi
    grep 'app.py' "$TMPDIR/deleted.log"
    test -f app.py
    touch $out
  ''
