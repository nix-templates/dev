# Additional ecosystems keep runtime-loaded analyzers in the application graph.
{
  metadata,
  pkgs,
  lib,
  options,
  version,
}:
let
  ruby = options.ruby or pkgs.ruby_3_4;
  php = options.php or pkgs.php;
  crystal = options.crystal or pkgs.crystal;
  rebar = options.rebar3 or pkgs.rebar3;
  cabal = options.cabal or pkgs.cabal-install;
  lein = options.leiningen or pkgs.leiningen;
  julia = options.julia or pkgs.julia;
  dart = options.dart or pkgs.dart;
  cmake = options.cmake or pkgs.cmake;
  rTools = pkgs.rWrapper.override {
    packages = with pkgs.rPackages; [
      lintr
      styler
    ];
  };
  rubySetup = ''
    export BUNDLE_FROZEN=true
    project_ruby() { "''${DVT_PROJECT_RUBY:-${ruby}/bin/ruby}" "$@"; }
    if [ -f .ruby-version ]; then
      expected=$(tr -d '[:space:]' < .ruby-version)
      actual=$(project_ruby -e 'print RUBY_VERSION')
      expected="''${expected#ruby-}"
      case "$actual" in "$expected" | "$expected".*) ;; *) echo "Ruby $actual does not match $expected; set DVT_PROJECT_RUBY" >&2; exit 1 ;; esac
    fi
  '';
  phpSetup = ''project_php() { "''${DVT_PROJECT_PHP:-${php}/bin/php}" "$@"; }'';
  rubyRunner = options.rubyTestRunner or metadata.testRunner;
in
{
  rack = {
    setup = rubySetup;
    quality = ''
      for_each '*.rb' project_ruby -c
      if [ -f .rubocop.yml ]; then run project_ruby -S bundle exec rubocop --fail-level warning; fi
    '';
    style = ''
      if [ -f .rubocop.yml ]; then
        run project_ruby -S bundle exec rubocop --autocorrect-all --fail-level fatal
      else
        run ${pkgs.rubocop}/bin/rubocop --config ${pkgs.writeText "standalone-ruby-style.yml" "{}"} --autocorrect-all --fail-level fatal
      fi
    '';
    tests =
      assert lib.assertMsg (lib.elem rubyRunner [
        "rake"
        "rspec"
      ]) "rubyTestRunner must be rake or rspec";
      "run project_ruby -S bundle exec ${rubyRunner}${lib.optionalString (rubyRunner == "rake") " test"}";
    replace = [
      "quality"
      "style"
      "tests"
    ];
  };
  phpunit = {
    setup = phpSetup;
    quality = ''
      for_each '*.php' project_php -l
      if [ -f phpstan.neon ] || [ -f phpstan.neon.dist ]; then
        run project_php vendor/bin/phpstan analyse --no-progress
      fi
      if [ -f psalm.xml ] || [ -f psalm.xml.dist ]; then
        run project_php vendor/bin/psalm --no-progress
      fi
    '';
    style = ''
      if [ -f .php-cs-fixer.php ] || [ -f .php-cs-fixer.dist.php ]; then
        run project_php vendor/bin/php-cs-fixer fix .
      elif [ -f phpcs.xml ] || [ -f phpcs.xml.dist ] || [ -f .phpcs.xml ]; then
        run project_php vendor/bin/phpcbf
      else
        echo 'Framework style requires the existing PHP-CS-Fixer or PHPCS configuration and tool.' >&2
        status=1
      fi
    '';
    tests = "run project_php vendor/bin/${metadata.testRunner}${
      lib.optionalString (metadata.testRunner == "codecept") " run"
    }";
    # Generic PHP analyzers may load incompatible plugins. Use project tools.
    architecture = ''
      if [ -f deptrac.yaml ] || [ -f deptrac.yml ]; then
        run project_php vendor/bin/deptrac analyse --no-progress
      fi
    '';
    replace = [
      "quality"
      "style"
      "tests"
      "architecture"
    ];
  };
  crystal = {
    tools = [
      crystal
      pkgs.ameba
      pkgs.crystalline
    ];
    setup = "export KEMAL_ENV=test AMBER_ENV=test";
    quality = ''
      run ${crystal}/bin/crystal tool format --check
      run ${pkgs.ameba}/bin/ameba
    '';
    style = "run ${crystal}/bin/crystal tool format";
    tests = "run ${crystal}/bin/crystal spec --order random";
    replace = [
      "tools"
      "quality"
      "style"
      "tests"
    ];
  };
  erlang = {
    setup = "export REBAR_OFFLINE=1";
    quality = "run ${rebar}/bin/rebar3 compile";
    tests = "run ${rebar}/bin/rebar3 eunit";
    architecture = "run ${rebar}/bin/rebar3 xref";
    replace = [
      "quality"
      "tests"
      "architecture"
    ];
  };
  clojure = {
    tests = "run ${lein}/bin/lein -o test";
    setup = "unset CLASSPATH JAVA_TOOL_OPTIONS";
    replace = [ "tests" ];
  };
  haskell = {
    tests = "run ${cabal}/bin/cabal test all --offline --test-show-details=direct";
    replace = [ "tests" ];
  };
  r = {
    tools = [ rTools ];
    quality = ''
      run env -u R_LIBS -u R_LIBS_USER -u R_LIBS_SITE ${rTools}/bin/Rscript --vanilla -e 'x <- lintr::lint_dir("."); print(x); if (length(x)) quit(status=1)'
    '';
    style = ''
      run env -u R_LIBS -u R_LIBS_USER -u R_LIBS_SITE ${rTools}/bin/Rscript --vanilla -e 'styler::style_dir(".")'
    '';
    # Explicit runtime/library paths prevent the tool R installation's packages
    # from being used as application dependencies; --vanilla disables renv bootstrap.
    setup = ''
      project_r() {
        if [ -z "''${DVT_PROJECT_RSCRIPT:-}" ] || [ -z "''${DVT_PROJECT_R_LIBRARY:-}" ]; then
          echo 'Set DVT_PROJECT_RSCRIPT and DVT_PROJECT_R_LIBRARY to the existing R runtime and library.' >&2
          return 127
        fi
        env -u R_LIBS -u R_LIBS_SITE R_LIBS_USER="$DVT_PROJECT_R_LIBRARY" "$DVT_PROJECT_RSCRIPT" --vanilla "$@"
      }
    '';
    tests = ''
      run project_r -e ${lib.escapeShellArg ''
        .libPaths(c(Sys.getenv("DVT_PROJECT_R_LIBRARY"), .Library))
        v <- as.character(utils::packageVersion("${metadata.package}"))
        if (!(v == "${version}" || startsWith(v, "${version}."))) stop("installed framework version differs from selected profile")
        if (file.exists("DESCRIPTION")) testthat::test_local(stop_on_failure=TRUE) else testthat::test_dir("tests/testthat", stop_on_failure=TRUE)
      ''}
    '';
    replace = [
      "tools"
      "quality"
      "style"
      "tests"
    ];
  };
  julia = {
    setup = ''
      export JULIA_PKG_OFFLINE=true JULIA_LOAD_PATH='@:@stdlib'
      project_julia() { "''${DVT_PROJECT_JULIA:-${julia}/bin/julia}" --startup-file=no --project=${
        lib.escapeShellArg (options.juliaTestProject or ".")
      } "$@"; }
    '';
    quality = "run project_julia -e 'using ${metadata.package}' ";
    tests = "run project_julia test/runtests.jl";
    replace = [
      "quality"
      "tests"
    ];
  };
  perl = {
    setup = ''
      project_perl() {
        if [ -z "''${DVT_PROJECT_PERL:-}" ]; then
          echo 'Set DVT_PROJECT_PERL to the interpreter used for the existing local/lib/perl5 dependencies.' >&2
          return 127
        fi
        env -u PERL5LIB -u PERL5OPT "$DVT_PROJECT_PERL" -Ilocal/lib/perl5 -Ilib "$@"
      }
    '';
    tests = ''run project_perl -MTAP::Harness -e 'exit(TAP::Harness->new({lib => ["local/lib/perl5", "lib"]})->runtests(sort glob "t/*.t")->has_errors ? 1 : 0)' '';
    replace = [ "tests" ];
  };
  dart = {
    tools = [ dart ];
    quality = "run ${dart}/bin/dart analyze --fatal-infos";
    style = "run ${dart}/bin/dart format .";
    tests = ''
      test_entry=$(${pkgs.python3}/bin/python3 -I -B ${./dart-test-path.py})
      run ${dart}/bin/dart --disable-dart-dev --packages=.dart_tool/package_config.json "$test_entry"
    '';
    architecture = ''
      if has dependency_validator pubspec.yaml; then
        entry=$(${pkgs.python3}/bin/python3 -I -B ${./dart-test-path.py} dependency_validator)
        run ${dart}/bin/dart --disable-dart-dev --packages=.dart_tool/package_config.json "$entry"
      fi
    '';
    replace = [
      "tools"
      "quality"
      "style"
      "tests"
      "architecture"
    ];
  };
  cmake = {
    tools = with pkgs; [
      cmake
      clang-tools
      cppcheck
      codespell
      flawfinder
      gcovr
    ];
    quality = ''
      run cppcheck --enable=warning,performance,portability --inline-suppr --suppress=missingIncludeSystem --error-exitcode=1 -i build -i .direnv .
      run run-clang-tidy -p ${lib.escapeShellArg (options.cmakeBuildDirectory or "build")}
    '';
    tests = "run ${cmake}/bin/ctest --test-dir ${
      lib.escapeShellArg (options.cmakeBuildDirectory or "build")
    } --output-on-failure --no-tests=error";
    replace = [
      "tools"
      "quality"
      "tests"
    ];
  };
}
