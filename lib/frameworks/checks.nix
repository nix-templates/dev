{
  pkgs,
  lib,
  dev,
}:
let
  profiles = lib.concatLists (
    lib.mapAttrsToList (
      name: profile: map (version: { inherit name version; }) profile.versions
    ) dev.frameworks
  );
  project =
    profile:
    dev.mkProject {
      inherit pkgs;
      frameworks = [ profile ];
    };
  django = project {
    name = "django";
    version = "5.2";
  };
  fixturePackages = import ./tests/packages.nix { inherit pkgs; };
  matrix = lib.mapAttrs' (
    name: profile:
    lib.nameValuePair name (
      lib.genAttrs profile.versions (
        version:
        let
          runtime = pkgs.python312.withPackages (
            ps:
            [ fixturePackages.${name}.${version} ]
            ++ lib.optionals (name != "django") [
              ps.pytest
              ps.httpx
            ]
          );
          commands = project { inherit name version; };
          runTests = pkgs.writeShellApplication {
            name = "framework-tests";
            text = commands.texts.tests;
            excludeShellChecks = [ "SC2329" ];
          };
          # Run the profile's own quality and style steps against real framework
          # source, in addition to the language checks validated elsewhere.
          module = dev.frameworks.${name}.module {
            inherit pkgs lib;
            options.frameworkVersion = version;
          };
          profileChecks = pkgs.writeShellApplication {
            name = "framework-tools";
            runtimeInputs = [
              pkgs.ruff
              pkgs.python313Packages.vulture
            ];
            text =
              builtins.readFile ../helpers.sh
              + ''
                project_python() {
                  env -u PYTHONPATH -u PYTHONHOME PYTHONNOUSERSITE=1 "$DVT_PROJECT_PYTHON" "$@"
                }
              ''
              + (module.style or "")
              + (module.quality or "")
              + ''
                exit "$status"
              '';
            excludeShellChecks = [ "SC2329" ];
          };
        in
        pkgs.runCommand "${name}-${version}-compatibility"
          {
            nativeBuildInputs = [
              runtime
              pkgs.coreutils
            ];
          }
          ''
            export PYTHONDONTWRITEBYTECODE=1
            export DVT_PROJECT_PYTHON=${runtime}/bin/python
            ${
              if name == "django" then
                ''
                  cp ${./tests/manage.py} manage.py
                  cp ${./tests/test_app.py} test_app.py
                ''
              else
                ''
                  cp ${./tests + "/test_${name}.py"} test_app.py
                ''
            }
            ${runTests}/bin/framework-tests > tests.log 2>&1 || { cat tests.log; exit 1; }
            ${lib.optionalString (name == "django") "grep 'Ran 1 test' tests.log"}
            ${lib.optionalString (name != "django") "grep '1 passed' tests.log"}
            ${profileChecks}/bin/framework-tools
            # A configured framework-loading checker must not fall back to a
            # different checker on PATH when the project lacks that module.
            export PATH=${pkgs.writeShellScriptBin "mypy" "exit 0"}/bin:$PATH
            echo '[tool.mypy]' > pyproject.toml
            if ${profileChecks}/bin/framework-tools > mypy.log 2>&1; then
              echo 'configured mypy silently used a foreign interpreter'; exit 1
            fi
            grep 'No module named mypy' mypy.log
            touch $out
          ''
      )
    )
  ) (lib.filterAttrs (_: profile: (profile.validation or "") == "framework-fixture") dev.frameworks);
  nodeMatrix = import ./tests/node-checks.nix {
    inherit
      pkgs
      lib
      dev
      profiles
      ;
  };
  djangoPython = pkgs.python313.withPackages (ps: [ ps.django ]);
  mismatchCommand = pkgs.writeShellApplication {
    name = "django-mismatch";
    text =
      (project {
        name = "django";
        version = "4.2";
      }).texts.tests;
    excludeShellChecks = [ "SC2329" ];
  };
  testCommand = pkgs.writeShellApplication {
    name = "django-tests";
    text = django.texts.tests;
    excludeShellChecks = [ "SC2329" ];
  };
in
{
  framework-python-adapters = import ./tests/python-adapters.nix { inherit pkgs lib dev; };

  style-check-regressions = import ./tests/style-checks.nix { inherit pkgs dev; };

  workspace-checks = import ./tests/workspace-checks.nix { inherit pkgs lib dev; };

  configured-project-checks = import ./tests/configured-checks.nix { inherit pkgs lib dev; };

  framework-native = import ./tests/native-checks.nix { inherit pkgs lib dev; };

  framework-node = pkgs.linkFarmFromDrvs "framework-node" nodeMatrix;

  framework-versions = pkgs.linkFarmFromDrvs "framework-versions" (
    lib.concatMap builtins.attrValues (builtins.attrValues matrix)
  );

  framework-composition =
    assert lib.assertMsg (
      !(builtins.elem "coverage" django.testModes)
    ) "Django inherited the language test runner";
    assert lib.assertMsg (lib.hasInfix "manage.py test" django.texts.tests)
      "Django test runner missing";
    assert lib.assertMsg (
      !(lib.hasInfix "python -m pytest" django.texts.tests)
    ) "Django used the tooling Python";
    assert lib.assertMsg (lib.hasInfix "deptry" django.texts.architecture)
      "Django lost language architecture checks";
    assert lib.assertMsg (
      !(builtins.tryEval (
        (project {
          name = "django";
          version = "99.0";
        }).testModes
      )).success
    ) "Unknown framework version was accepted";
    pkgs.runCommand "framework-composition" { } "touch $out";

  framework-scripts = pkgs.linkFarmFromDrvs "framework-scripts" (
    lib.concatMap (
      profile:
      lib.mapAttrsToList (
        name: text:
        pkgs.writeShellApplication {
          name = "${profile.name}-${profile.version}-${name}";
          text = builtins.unsafeDiscardStringContext text;
          excludeShellChecks = [ "SC2329" ];
        }
      ) (project profile).texts
    ) profiles
  );

  framework-runtime =
    pkgs.runCommand "framework-runtime"
      {
        nativeBuildInputs = [
          djangoPython
          pkgs.coreutils
        ];
      }
      ''
        mkdir fixture
        cd fixture
        cp ${./tests/manage.py} manage.py
        cp ${./tests/test_app.py} test_app.py
        chmod u+w test_app.py
        export PYTHONDONTWRITEBYTECODE=1
        export DVT_PROJECT_PYTHON=${djangoPython}/bin/python
        # A foreign Python environment must not leak into the application.
        mkdir foreign
        echo 'raise RuntimeError("foreign Python leaked")' > foreign/sitecustomize.py
        export PYTHONPATH="$PWD/foreign"
        ${testCommand}/bin/django-tests > passed 2>&1
        grep 'Ran 1 test' passed
        if ${mismatchCommand}/bin/django-mismatch > mismatch 2>&1; then
          echo 'a mismatched framework version passed'; exit 1
        fi
        grep 'does not match installed' mismatch
        sed -i 's/2 + 2, 4/2 + 2, 5/' test_app.py
        if ${testCommand}/bin/django-tests > failed 2>&1; then
          echo 'a failing application test passed'; exit 1
        fi
        grep 'FAILED' failed
        export DVT_PROJECT_PYTHON="$PWD/missing-python"
        if ${testCommand}/bin/django-tests > missing 2>&1; then
          echo 'missing project environment passed'; exit 1
        fi
        grep 'project Python is missing' missing
        touch $out
      '';
}
