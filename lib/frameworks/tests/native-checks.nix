{
  pkgs,
  lib,
  dev,
}:
let
  fakeProgram = pkgs.writeShellScript "framework-runtime" ''
    if [ "''${1:-}" = --version ]; then
      echo '{"frameworkVersion":"3.38.0"}'
    elif [ "''${1:-}" = -e ]; then
      printf 3.4.6
    else
      echo "$*" >> "$DVT_DISPATCH_LOG"
      echo "GOFLAGS=''${GOFLAGS:-};GOTOOLCHAIN=''${GOTOOLCHAIN:-};BUNDLE_FROZEN=''${BUNDLE_FROZEN:-}" >> "$DVT_DISPATCH_LOG"
      exit "''${DVT_DISPATCH_FAIL:-0}"
    fi
  '';
  fakeRuntime = pkgs.runCommand "framework-dispatch-runtime" { } ''
    mkdir -p $out/bin
    for name in ruby php go cargo swift dotnet flutter mix crystal rebar3 lein cabal julia Rscript perl dart ctest; do
      ln -s ${fakeProgram} "$out/bin/$name"
    done
  '';
  profiles = lib.concatLists (
    lib.mapAttrsToList (
      name: metadata:
      lib.optionals ((metadata.adapter or "") == "native") (
        map (version: {
          inherit name version;
          metadata = metadata // (metadata.variants.${version} or { });
        }) metadata.versions
      )
    ) dev.frameworks
  );
  commands = map (
    profile:
    let
      project = dev.mkProject {
        inherit pkgs;
        frameworks = [ { inherit (profile) name version; } ];
        options = {
          ruby = fakeRuntime;
          php = fakeRuntime;
          go = fakeRuntime;
          dotnetSdk = fakeRuntime;
          flutter = fakeRuntime;
          crystal = fakeRuntime;
          rebar3 = fakeRuntime;
          leiningen = fakeRuntime;
          cabal = fakeRuntime;
          julia = fakeRuntime;
          dart = fakeRuntime;
          cmake = fakeRuntime;
        };
      };
      command = pkgs.writeShellApplication {
        name = "framework-tests";
        text = project.texts.tests;
        excludeShellChecks = [ "SC2329" ];
      };
      expected =
        {
          rails = "bin/rails test";
          laravel = "artisan test --no-interaction";
          symfony = "vendor/bin/phpunit";
          phoenix = "test";
          jvm = "--offline --no-daemon test";
          go = "test ./...";
          rust = "test --locked";
          vapor = "test --disable-automatic-resolution";
          dotnet = "test --no-restore";
          flutter = "test --no-pub";
          rack = "-S bundle exec ${profile.metadata.testRunner}${
            lib.optionalString (profile.metadata.testRunner == "rake") " test"
          }";
          phpunit = "vendor/bin/${profile.metadata.testRunner}${
            lib.optionalString (profile.metadata.testRunner == "codecept") " run"
          }";
          crystal = "spec --order random";
          erlang = "eunit";
          clojure = "-o test";
          haskell = "test all --offline --test-show-details=direct";
          r = "--vanilla -e";
          julia = "--startup-file=no --project=. test/runtests.jl";
          perl = "-Ilocal/lib/perl5 -Ilib -MTAP::Harness";
          dart = "--disable-dart-dev --packages=.dart_tool/package_config.json";
          cmake = "--test-dir build --output-on-failure --no-tests=error";
        }
        .${profile.metadata.recipe};
    in
    ''
      mkdir ${profile.name}-${profile.version}
      pushd ${profile.name}-${profile.version} >/dev/null
      python3 ${./native-fixture.py} ${profile.metadata.kind} ${profile.metadata.package} ${profile.version}
      ln -s ${fakeProgram} gradlew
      export DVT_DISPATCH_LOG="$PWD/dispatch.log"
      find . -type f ! -name '*.log' -exec sha256sum {} \; | sort > "$TMPDIR/before"
      ${command}/bin/framework-tests > passed.log 2>&1 || { cat passed.log; exit 1; }
      grep -F -- ${lib.escapeShellArg expected} dispatch.log
      ${lib.optionalString (
        profile.metadata.recipe == "go"
      ) "grep -F 'GOFLAGS=-mod=readonly;GOTOOLCHAIN=local' dispatch.log"}
      ${lib.optionalString (
        profile.metadata.recipe == "rails"
      ) "grep -F 'BUNDLE_FROZEN=true' dispatch.log"}
      export DVT_DISPATCH_FAIL=1
      if ${command}/bin/framework-tests > failed.log 2>&1; then
        echo '${profile.name} ignored a failing project test command'; exit 1
      fi
      unset DVT_DISPATCH_FAIL
      find . -type f ! -name '*.log' -exec sha256sum {} \; | sort > "$TMPDIR/after"
      diff "$TMPDIR/before" "$TMPDIR/after"
      ${lib.optionalString (profile.metadata.kind != "flutter") ''
        python3 ${./native-fixture.py} ${profile.metadata.kind} ${profile.metadata.package} 999
        rm dispatch.log
        if ${command}/bin/framework-tests > mismatch.log 2>&1; then
          echo '${profile.name} accepted a mismatched dependency'; exit 1
        fi
        test ! -e dispatch.log
        grep 'does not match' mismatch.log
      ''}
      popd >/dev/null
    ''
  ) profiles;
in
pkgs.runCommand "framework-native"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.coreutils
      pkgs.diffutils
      pkgs.findutils
      pkgs.gnugrep
    ];
  }
  ''
    export PATH=${fakeRuntime}/bin:$PATH
    export DVT_PROJECT_RSCRIPT=${fakeRuntime}/bin/Rscript
    export DVT_PROJECT_R_LIBRARY="$TMPDIR/project-library"
    export DVT_PROJECT_PERL=${fakeRuntime}/bin/perl
    export PYTHONDONTWRITEBYTECODE=1
    ${lib.concatStrings commands}
    touch $out
  ''
