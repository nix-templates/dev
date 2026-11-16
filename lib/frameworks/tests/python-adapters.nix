{
  pkgs,
  lib,
  dev,
}:
let
  profiles = lib.concatLists (
    lib.mapAttrsToList (
      name: metadata:
      lib.optionals ((metadata.adapter or "") == "python") (
        map (version: { inherit name metadata version; }) metadata.versions
      )
    ) dev.frameworks
  );
  runtime = pkgs.python3.withPackages (ps: [ ps.pytest ]);
  cases = map (
    profile:
    let
      command = pkgs.writeShellApplication {
        name = "framework-tests";
        text =
          (dev.mkProject {
            inherit pkgs;
            frameworks = [ { inherit (profile) name version; } ];
          }).texts.tests;
        excludeShellChecks = [ "SC2329" ];
      };
    in
    ''
      mkdir ${profile.name}-${profile.version}
      pushd ${profile.name}-${profile.version} >/dev/null
      # Only metadata is synthesized. The project interpreter and pytest are real.
      mkdir ${profile.name}-${profile.version}.dist-info
      printf 'Name: ${profile.metadata.distribution}\nVersion: ${profile.version}.0\n' > ${profile.name}-${profile.version}.dist-info/METADATA
      echo 'def test_success(): assert 1 + 1 == 2' > test_app.py
      ${lib.optionalString
        (lib.elem profile.name [
          "mkdocs"
          "scrapy"
        ])
        ''
            cat > ${profile.name}.py <<'PY'
          import os, sys
          assert sys.argv[1:] == ${if profile.name == "mkdocs" then "['build', '--strict']" else "['check']"}
          sys.exit(int(os.environ.get('DVT_TEST_FAIL', '0')))
          PY
        ''
      }
      echo '# unchanged manifest' > pyproject.toml
      echo 'unchanged lock' > uv.lock
      export DVT_PROJECT_PYTHON=${runtime}/bin/python
      ${command}/bin/framework-tests > pass.log 2>&1 || { cat pass.log; exit 1; }
      echo 'def test_failure(): assert False' > test_app.py
      export DVT_TEST_FAIL=1
      if ${command}/bin/framework-tests > fail.log 2>&1; then echo 'failing tests were ignored'; exit 1; fi
      unset DVT_TEST_FAIL
      sed -i 's/Version:.*/Version: 999.0/' ${profile.name}-${profile.version}.dist-info/METADATA
      if ${command}/bin/framework-tests > mismatch.log 2>&1; then echo 'version mismatch was ignored'; exit 1; fi
      grep 'does not match' mismatch.log
      test "$(cat pyproject.toml)" = '# unchanged manifest'
      test "$(cat uv.lock)" = 'unchanged lock'
      popd >/dev/null
    ''
  ) profiles;
in
pkgs.runCommand "framework-python-adapters"
  {
    nativeBuildInputs = [
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.gnused
    ];
  }
  ''
    export PYTHONDONTWRITEBYTECODE=1
    ${lib.concatStrings cases}
    touch $out
  ''
