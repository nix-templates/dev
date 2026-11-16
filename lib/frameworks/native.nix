# Native framework checks load the project's existing dependency graph. They
# never install a second framework or inject tool plugins into that graph.
baseMetadata:
{
  pkgs,
  lib,
  options,
  ...
}:
let
  version = options.frameworkVersion or baseMetadata.defaultVersion;
  metadata = baseMetadata // (baseMetadata.variants.${version} or { });
  recipe = metadata.recipe;
  ruby = options.ruby or pkgs.ruby_3_4;
  php = options.php or pkgs.php;
  go = options.go or pkgs.go;
  flutter = options.flutter or pkgs.flutter;
  recipes = {
    dotnet =
      let
        sdk = options.dotnetSdk or pkgs.${"dotnet-sdk_${metadata.sdkVersion or version}"};
      in
      {
        tools = [
          sdk
        ]
        ++ lib.optionals (lib.elem "fsharp" metadata.languages) [
          pkgs.fantomas
          pkgs.fsautocomplete
        ]
        ++ lib.optionals (lib.elem "csharp" metadata.languages) [ pkgs.omnisharp-roslyn ];
        quality = "run ${sdk}/bin/dotnet build --no-restore --warnaserror";
        style =
          if lib.elem "fsharp" metadata.languages then
            "run ${pkgs.fantomas}/bin/fantomas ."
          else
            "run ${sdk}/bin/dotnet format --no-restore";
        tests = "run ${sdk}/bin/dotnet test --no-restore";
        replace = [
          "tools"
          "quality"
          "style"
          "tests"
        ];
      };
    rails = {
      quality = ''
        run project_ruby bin/rails zeitwerk:check
        if [ -e .rubocop.yml ]; then
          run project_ruby -S bundle exec rubocop --fail-level warning
        fi
      '';
      style = ''
        if [ -e .rubocop.yml ] || [ -x bin/rubocop ]; then
          run project_ruby -S bundle exec rubocop --autocorrect-all --fail-level fatal
        else
          run ${pkgs.rubocop}/bin/rubocop --config ${pkgs.writeText "standalone-ruby-style.yml" "{}"} --autocorrect-all --fail-level fatal
        fi
      '';
      tests = "run project_ruby bin/rails test";
      setup = ''
        export BUNDLE_FROZEN=true
        project_ruby() { "''${DVT_PROJECT_RUBY:-${ruby}/bin/ruby}" "$@"; }
        if [ -f .ruby-version ]; then
          expected=$(tr -d '[:space:]' < .ruby-version)
          actual=$(project_ruby -e 'print RUBY_VERSION')
          expected="''${expected#ruby-}"
          case "$actual" in
            "$expected" | "$expected".*) ;;
            *)
              echo "Ruby $actual does not match .ruby-version $expected; set DVT_PROJECT_RUBY" >&2
              exit 1
              ;;
          esac
        fi
      '';
      replace = [
        "quality"
        "style"
        "tests"
      ];
    };
    laravel = {
      quality = ''
        for_each '*.php' project_php -l
        run project_php artisan route:list --no-interaction
        if [ -x vendor/bin/phpstan ]; then
          run project_php vendor/bin/phpstan analyse --no-progress
        else
          echo ":: skipping project PHPStan (not installed in the existing bundle)"
        fi
      '';
      style = "run project_php vendor/bin/pint";
      tests = "run project_php artisan test --no-interaction";
      setup = ''project_php() { "''${DVT_PROJECT_PHP:-${php}/bin/php}" "$@"; }'';
      replace = [
        "quality"
        "style"
        "tests"
      ];
    };
    symfony = {
      quality = "run project_php bin/console lint:container --no-debug --no-interaction";
      style = "run project_php vendor/bin/php-cs-fixer fix .";
      tests = "run project_php vendor/bin/phpunit";
      setup = ''project_php() { "''${DVT_PROJECT_PHP:-${php}/bin/php}" "$@"; }'';
      replace = [
        "quality"
        "style"
        "tests"
      ];
    };
    phoenix = {
      quality = "run mix compile --warnings-as-errors --no-deps-check";
      style = "run mix format";
      tests = "run mix test";
      replace = [
        "quality"
        "style"
        "tests"
      ];
    };
    jvm = {
      quality = "run project_build compile";
      architecture = ''
        if has maven-enforcer-plugin pom.xml; then run project_build enforcer:enforce; fi
        if has com.autonomousapps.dependency-analysis build.gradle build.gradle.kts settings.gradle settings.gradle.kts; then
          run project_build buildHealth
        fi
      '';
      tests = "run project_build test";
      setup = ''
        # Use the build wrapper and plugins already pinned by the project.
        # No global Lombok agent or unrelated CLASSPATH is injected.
        unset JAVA_TOOL_OPTIONS CLASSPATH
        export JAVA_HOME=${options.java or pkgs.jdk17}
        export PATH="$JAVA_HOME/bin:$PATH"
        project_build() {
          if [ -x ./mvnw ]; then
            ./mvnw --offline --batch-mode "$@"
          elif [ -x ./gradlew ]; then
            if [ "$1" = compile ]; then
              shift
              ./gradlew --offline --no-daemon classes "$@"
            else
              ./gradlew --offline --no-daemon "$@"
            fi
          else
            echo "A project Maven or Gradle wrapper is required; no build tool or plugin was installed." >&2
            return 1
          fi
        }
      '';
      replace = [
        "quality"
        "tests"
        "shellHook"
        "architecture"
      ];
    };
    go = {
      quality = "run ${go}/bin/go vet ./...";
      tests = "run ${go}/bin/go test ./...";
      setup = ''
        export GOTOOLCHAIN=local
        export GOFLAGS="''${GOFLAGS:+$GOFLAGS }-mod=readonly"
      '';
      replace = [
        "quality"
        "tests"
      ];
    };
    rust = {
      # All rust tools come from the same project-selected toolchain. Cargo's
      # locked mode refuses to repair or replace the application's lockfile.
      quality = "run cargo clippy --locked --all-targets -- --deny warnings";
      tests = "run cargo test --locked";
      security = ''
        when Cargo.lock cargo audit
        when deny.toml cargo deny --locked check
      '';
      replace = [
        "quality"
        "tests"
        "security"
      ];
    };
    flutter = {
      tools = [ flutter ];
      quality = "run ${flutter}/bin/flutter analyze --no-pub --fatal-infos";
      style = "run ${flutter}/bin/dart format .";
      tests = "run ${flutter}/bin/flutter test --no-pub";
      replace = [
        "tools"
        "quality"
        "style"
        "tests"
        "architecture"
      ];
    };
    vapor = {
      tests = "run swift test --disable-automatic-resolution";
      replace = [ "tests" ];
    };
  };
  baseSelected =
    (
      recipes
      // (import ./native-extra.nix {
        inherit
          metadata
          pkgs
          lib
          options
          version
          ;
      })
    ).${recipe};
  runtimeArchitecture =
    if metadata.kind == "gem" then
      ''
        when packwerk.yml project_ruby -S bundle exec packwerk check
      ''
    else if metadata.kind == "composer" then
      ''
        if [ -f deptrac.yaml ] || [ -f deptrac.yml ]; then
          run project_php vendor/bin/deptrac analyse --no-progress
        fi
      ''
    else if metadata.kind == "cargo" then
      ''
        when deny.toml cargo deny --locked check bans
      ''
    else
      null;
  selected =
    baseSelected
    // lib.optionalAttrs (runtimeArchitecture != null) {
      architecture = runtimeArchitecture;
      replace = lib.unique (baseSelected.replace ++ [ "architecture" ]);
    };
  guard = ''
    ${pkgs.python3}/bin/python3 -I -B ${./version_guard.py} ${lib.escapeShellArg metadata.kind} ${
      lib.escapeShellArg (
        if metadata.kind == "flutter" then "${flutter}/bin/flutter" else metadata.package
      )
    } ${lib.escapeShellArg version}
  '';
in
{
  tools = selected.tools or [ ];
  preflight = guard + (selected.setup or "") + "\n";
  replace = lib.genAttrs (metadata.replaceLanguages or metadata.languages) (_: selected.replace);
  quality = (selected.quality or "") + "\n";
  style = (selected.style or "") + "\n";
  security = (selected.security or "") + "\n";
  architecture = lib.optional (selected ? architecture) ((selected.architecture or "") + "\n");
  tests.run = [ ((selected.tests or "") + "\n") ];
}
