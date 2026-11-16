# Framework profiles and tool isolation

`dvt init` discovers existing projects; `dvt init <framework-or-language>`
selects an explicit profile or language default. Both generate development tooling. It does not
create the application, install its dependencies, or edit its dependency
manifests, lockfiles, or existing tool configuration. Initialization writes
only `flake.nix` and `.envrc`, and preflights conflicts before either write.
Use `--dry-run` to inspect the files when integrating an existing flake.

```sh
dvt inspect
dvt init --dry-run
dvt init
dvt list
dvt init django --framework-version 4.2
dvt init nextjs --framework-version 16
dvt init rails --framework-version 7.2
dvt init rust
dvt describe kotlin
```

## Discovery and existing tools

Discovery walks source files using the existing language detector, respects Git
ignore rules and excludes dependency/build directories. Manifest directories form
components; `--exclude <path>` omits examples or unrelated projects. `dvt inspect`
reports languages, framework selections, configuration evidence and warnings as
JSON. It never imports JavaScript configuration, loads application code or runs
package scripts during discovery.

Canonical package/composer scripts (`quality`, `style`, `security`,
`architecture`, `tests`) take precedence. Existing conventional script names are
also recognized without renaming them. Recognized native configurations select
the owning tool: ESLint/Biome, Ruff/mypy, PHPStan/Psalm, RuboCop, Semgrep,
import-linter/deptry, dependency-cruiser/knip, Deptrac, Packwerk, Cargo bans,
Gradle dependency analysis and Maven Enforcer, among others. Configured categories
replace that category’s default checks. Tools can be added explicitly to the
reviewable `configured` entries in the flake when discovery has no adapter.

Configured Python console tools run through the existing project interpreter;
Node tools resolve installed local or declared workspace binaries, including
hoisted dependencies. npm, pnpm and Yarn locks support version discovery.
Ambiguous lock versions are rejected. Yarn PnP execution uses an existing `yarnPath` binary or
`DVT_PROJECT_YARN`; no Corepack download is triggered. PnP configurations with
absolute or workspace-relative paths may require a native check-mode command
instead of the generic `style --check` source copy. Native wrappers retain their project configuration. Standalone executables
prefer `.venv/bin`, `.tools/bin`, `.bin` or `bin`, then the component PATH.
Missing project plugins are never installed automatically.

A bare initialization requires resolved metadata for detected frameworks. It
fails on unknown release lines, conflicting versions or unresolved constraints.
Known host frameworks take precedence over underlying libraries; other overlaps
produce a warning for manual composition. Tox, Nox and pre-commit configurations
are reported without automatically creating their environments. Detection is
conservative and finite: review the report for custom build logic, inherited
configurations and tools that are not recognized yet.

Explicit framework initialization can use the registry default when no version
metadata exists; the selected line is always written into the flake. Language
names keep their default recipes. Unsupported names and release lines fail.

Generated workspaces expose the five root commands and `component-<path>` dev
shells. Each component command runs in its own working directory and process
environment. Run root commands from the repository root. Architecture dispatch
includes components with configured architecture checks or `architecture.toml`;
when none qualify it exits 2. Existing dependency/boundary tools work without
that optional file. The built-in engine remains available for projects that want
its source-based layer and purity rules.

## Environments

Three dependency graphs stay distinct:

1. **The application:** its existing dependencies, lockfile and runtime.
2. **The tooling:** Nix derivations with separately pinned interpreters, hosts,
   parsers, plugins and rules. Node bundles have their own package locks and
   Nix dependency hashes under `lib/frameworks/bundles/`. These packages never
   enter the application's `node_modules`.
3. **Test fixtures:** pinned framework distributions used to validate profiles.
   Test fixtures never enter generated development shells.

The project `flake.lock` pins Nix inputs; each Node tool bundle additionally
pins its npm closure. Python template tools use their own packaged interpreter.
Application Python commands clear foreign `PYTHONPATH`/`PYTHONHOME` and use
`.venv/bin/python`, or `DVT_PROJECT_PYTHON`. They verify framework metadata with
that interpreter before loading application code. No second Django, Flask or
FastAPI is installed into that environment.

When no project quality configuration is selected, Node framework quality uses
the profile's bundled configuration and plugins. Discovery selects existing
project quality tools instead when configured. The isolated fallback does not
merge arbitrary project ESLint plugins into its dependency graph. Prettier reads existing project configuration and reports
missing custom plugins instead of installing them. Configured frontend type checks use the project's existing `tsc` or `vue-tsc`,
which loads its actual framework types. Node tests and architecture helpers
use existing project dependencies. A missing helper fails; no package
manager is allowed to fetch a latest helper on demand.

Native framework checks use existing project entry points or build wrappers:
Rails `bin/rails`, Laravel `artisan`, Symfony `bin/console`, Phoenix `mix`, JVM
`mvnw`/`gradlew`, Go modules, Cargo, Swift packages and .NET projects. Composer
checks inspect installed metadata; Ruby, Cargo, Mix, Go and Swift inspect their
lock/manifest data. Maven/Gradle require an unambiguous explicit version.
Native project test runners and configured plugin-based checkers/formatters
must already be installed. Configured Rails RuboCop and Symfony PHP-CS-Fixer
run in the project graph, so they do not load framework plugins into an
unrelated globally installed checker.
This is necessary when a tool executes application code; isolated analyzers
cannot safely substitute their own framework or project dependency graph.

Cargo runs locked, Go refuses module edits, Maven/Gradle run offline, .NET skips
restore and Flutter skips pub resolution. These commands may write build output,
test databases or normal caches. No profile installs missing application or
optional test dependencies. Database, browser, container and hardware fixtures
remain explicit project setup.

## Separate package sets and older tools

An existing flake can compose profiles directly:

```nix
project = dev.lib.mkProject {
  inherit pkgs;
  languages = [ "python" "typescript" ];
  frameworks = [ { name = "django"; version = "4.2"; } ];
  options.projectPython = ".venv/bin/python";
  # options.django.managePy = "backend/manage.py";
  # options.django.testRunner = "pytest"; # existing project pytest/plugins
};
```

`toolPkgs` selects a separately pinned package set for language tooling without
changing application packages. Each framework selection may also carry its own
`toolPkgs`, so two projects can use different tool versions with the same profile:

```nix
project = dev.lib.mkProject {
  inherit pkgs;
  toolPkgs = tooling.legacyPackages.${system};
  frameworks = [ {
    name = "django";
    version = "4.2";
    toolPkgs = legacyTooling.legacyPackages.${system};
  } ];
};
```

Declare `tooling` and `legacyTooling` as separate flake inputs and commit their
locks. Do not make them follow the application package set when independent
updates are needed. Changing the tool lock remains an explicit, reviewable
upgrade; selecting a framework release line does not automatically fetch old
Nixpkgs or claim every tool revision is compatible with it.

Node profiles default to Node 22 for application commands, with `options.node`
available for a matching pinned runtime. Isolated analysis bundles keep their
own runtime. This avoids forcing the latest Node onto older framework CLIs;
[Angular's version matrix](https://angular.dev/reference/versions) is one example
of why runtime selection matters. Discovery does not yet solve every runtime
constraint or provision missing project dependencies.

Project runtime overrides include `DVT_PROJECT_PYTHON`, `DVT_PROJECT_RUBY` and
`DVT_PROJECT_PHP`. Nix options include `python`, `rustToolchain`, `options.java`,
`options.dotnetSdk`, `options.flutter`, `options.go`, `options.php` and
`options.ruby` where used by the corresponding profile. Pin these to match
existing runtime constraints. Ruby checks `.ruby-version`; Flutter honors an
explicit `.fvmrc` release. Framework profiles never create Python virtualenvs
on shell entry; `options.pythonVenv = true` is rejected for those profiles.
A configured framework-loading mypy check runs with the existing project mypy
and plugins through the project interpreter. It fails if they are missing;
the standalone Nix mypy is not substituted into that environment.

Custom profiles work for any language. Put a profile next to the project flake:

```nix
# my-framework.nix: profile metadata and a module with canonical command fields.
{
  languages = [ "ocaml" ];
  module = { pkgs, ... }: {
    # tools = [ anIsolatedToolPackage ];
    quality = "run my-framework-check\n";
    tests.run = [ "run my-existing-test-runner\n" ];
    # replace.ocaml = [ "tests" ]; # replace instead of append when needed
  };
}
```

Select it with `frameworks = [ ./my-framework.nix ];`. Module fields are
`tools`, `quality`, `style`, `security`, `architecture` (a list of blocks),
`tests` (blocks per mode), `defaults`, `preflight` and `replace`.
Version-aware modules receive `options.frameworkVersion`. Conflicting profiles
that replace the same language command are rejected; compose their behavior
explicitly in a custom profile. Existing tool configurations own architecture rules. The optional built-in
engine reads `architecture.toml`; initialization does not invent boundaries.

## Executable profiles and validation

Validation labels distinguish evidence:

- `framework-fixture`: real framework release lines execute application tests;
  Django also runs framework checks against each listed line.
- `tool-fixture`: every listed release-line tool bundle checks valid components,
  rejects invalid components and rejects mismatched installed framework metadata.
- `tool-and-adapter`: real isolated Node tools check components; project compiler
  commands use test doubles to verify dispatch, failure and missing-tool behavior.
- `project-adapter`: real Python/pytest with synthetic framework metadata checks
  environment ownership and dispatch, without full framework applications.
- `native-adapter`: version readers and command composition are tested and all
  generated scripts pass ShellCheck. Full application fixtures for every listed
  framework/runtime combination are not yet part of this repository.

An accepted release line describes the recipe and version guard, not a promise
that every plugin, project configuration, runtime patch or future tool update
has been tested. The table below makes the current evidence explicit.

Current coverage: **81 profiles, 120 release-line selections, 24 language modules**.
All 69 language modules also have defaults and research entries.

| Profile | Language defaults | Release lines | Validation | Primary source |
| :--- | :--- | :--- | :--- | :--- |
| `actix-web` | rust | 4 | native-adapter | [Documentation](https://actix.rs/docs/testing/) |
| `aiohttp` | python | 3 | project-adapter | [Documentation](https://docs.aiohttp.org/en/stable/testing.html) |
| `amber` | crystal | 1 | native-adapter | [Documentation](https://amberframework.org/docs/v1.5/guides/testing) |
| `angular` | typescript, node | 19, 20, 21, 22 | tool-and-adapter | [Documentation](https://angular.dev/reference/versions) |
| `ash` | elixir | 3 | native-adapter | [Documentation](https://hexdocs.pm/ash/testing.html) |
| `aspnetcore` | csharp | 8, 9, 10 | native-adapter | [Documentation](https://learn.microsoft.com/en-us/aspnet/core/testing/integration-testing) |
| `astro` | typescript, node | 5, 6 | tool-and-adapter | [Documentation](https://docs.astro.build/en/reference/cli-reference/) |
| `avalonia` | csharp | 11 | native-adapter | [Documentation](https://docs.avaloniaui.net/docs/testing/headless/) |
| `axum` | rust | 0.7, 0.8 | native-adapter | [Documentation](https://actix.rs/docs/testing/) |
| `cakephp` | php | 4, 5 | native-adapter | [Documentation](https://book.cakephp.org/5/en/development/testing.html) |
| `catch2` | c-cpp | 2, 3 | native-adapter | [Documentation](https://catch2-temp.readthedocs.io/en/latest/cmake-integration.html) |
| `chi` | go | 5 | native-adapter | [Documentation](https://github.com/go-chi/chi) |
| `codeigniter` | php | 4 | native-adapter | [Documentation](https://github.com/codeigniter4/CodeIgniter4/blob/develop/user_guide_src/source/testing/overview.rst) |
| `cowboy` | erlang | 2 | native-adapter | [Documentation](https://rebar3.org/docs/testing/) |
| `dancer2` | perl | 1 | native-adapter | [Documentation](https://metacpan.org/pod/Dancer2::Manual) |
| `django` | python | 4.2, 5.2, 6.0 | framework-fixture | [Documentation](https://docs.djangoproject.com/en/5.2/ref/django-admin/) |
| `docusaurus` | typescript, node | 3 | tool-and-adapter | [Documentation](https://docusaurus.io/docs/cli) |
| `drogon` | c-cpp | 1 | native-adapter | [Documentation](https://github.com/drogonframework/drogon/wiki/ENG-19-Testing-Framework) |
| `dropwizard` | java | 4 | native-adapter | [Documentation](https://www.dropwizard.io/en/stable/manual/testing.html) |
| `echo` | go | 4 | native-adapter | [Documentation](https://gin-gonic.com/en/docs/testing/) |
| `express` | typescript, node | 4, 5 | tool-and-adapter | [Documentation](https://expressjs.com/en/guide/migrating-5.html) |
| `falcon` | python | 4 | project-adapter | [Documentation](https://falcon.readthedocs.io/en/stable/api/testing.html) |
| `fastapi` | python | 0.115 | framework-fixture | [Documentation](https://fastapi.tiangolo.com/tutorial/testing/) |
| `fastify` | typescript, node | 4, 5 | tool-and-adapter | [Documentation](https://fastify.dev/docs/latest/Guides/Testing/) |
| `fiber` | go | 2, 3 | native-adapter | [Documentation](https://docs.gofiber.io/api/app/) |
| `flask` | python | 3.0, 3.1 | framework-fixture | [Documentation](https://flask.palletsprojects.com/en/stable/testing/) |
| `flutter` | dart | 3 | native-adapter | [Documentation](https://docs.flutter.dev/reference/flutter-cli) |
| `genie` | julia | 5 | native-adapter | [Documentation](https://github.com/GenieFramework/Genie.jl/tree/main/test) |
| `gin` | go | 1 | native-adapter | [Documentation](https://gin-gonic.com/en/docs/testing/) |
| `giraffe` | fsharp | 7, 8 | native-adapter | [Documentation](https://learn.microsoft.com/en-us/aspnet/core/testing/integration-testing) |
| `golem` | r | 0.5 | native-adapter | [Documentation](https://thinkr-open.github.io/golem/reference/testhelpers.html) |
| `googletest` | c-cpp | 1 | native-adapter | [Documentation](https://google.github.io/googletest/quickstart-cmake.html) |
| `grails` | groovy | 6, 7 | native-adapter | [Documentation](https://grails.apache.org/docs/latest/guide/testing.html) |
| `hanami` | ruby | 2 | native-adapter | [Documentation](https://hanakai.org/learn/hanami/v2.0/actions/testing) |
| `hono` | typescript, node | 4 | tool-and-adapter | [Documentation](https://hono.dev/docs/helpers/testing) |
| `hummingbird` | swift | 2 | native-adapter | [Documentation](https://github.com/hummingbird-project/hummingbird/tree/main/Tests) |
| `kemal` | crystal | 1 | native-adapter | [Documentation](https://github.com/kemalcr/spec-kemal) |
| `ktor` | kotlin | 2, 3 | native-adapter | [Documentation](https://ktor.io/docs/server-testing.html) |
| `laravel` | php | 11, 12, 13 | native-adapter | [Documentation](https://laravel.com/framework/docs/pint) |
| `litestar` | python | 2 | project-adapter | [Documentation](https://docs.litestar.dev/2/usage/testing.html) |
| `liveview` | elixir | 0.20, 1 | native-adapter | [Documentation](https://hexdocs.pm/phoenix_live_view/Phoenix.LiveViewTest.html) |
| `micronaut` | java | 4 | native-adapter | [Documentation](https://docs.micronaut.io/latest/guide/) |
| `mkdocs` | python, markdown | 1 | project-adapter | [Documentation](https://www.mkdocs.org/user-guide/cli/) |
| `mojolicious` | perl | 9 | native-adapter | [Documentation](https://docs.mojolicious.org/Test/Mojo) |
| `nestjs` | typescript, node | 10, 11 | tool-and-adapter | [Documentation](https://docs.nestjs.com/fundamentals/testing) |
| `nextjs` | typescript, node | 14, 15, 16 | tool-fixture | [Documentation](https://nextjs.org/docs/app/api-reference/config/eslint) |
| `nuxt` | typescript, node | 3, 4 | tool-and-adapter | [Documentation](https://nuxt.com/docs/4.x/api/commands/typecheck) |
| `pedestal` | clojure | 0.7 | native-adapter | [Documentation](https://pedestal.io/pedestal/0.7/guides/unit-testing.html) |
| `phoenix` | elixir | 1.7, 1.8 | native-adapter | [Documentation](https://phoenix.hexdocs.pm/testing.html) |
| `plumber` | r | 1 | native-adapter | [Documentation](https://github.com/rstudio/plumber) |
| `poem` | rust | 3 | native-adapter | [Documentation](https://docs.rs/poem/latest/poem/test/index.html) |
| `pyramid` | python | 2 | project-adapter | [Documentation](https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/testing.html) |
| `qt` | c-cpp | 5, 6 | native-adapter | [Documentation](https://doc.qt.io/qt-6/qttest-index.html) |
| `quarkus` | java | 3 | native-adapter | [Documentation](https://quarkus.io/guides/getting-started-testing/) |
| `rails` | ruby | 7.2, 8.0, 8.1 | native-adapter | [Documentation](https://guides.rubyonrails.org/command_line.html) |
| `react` | typescript, node | 18, 19 | tool-fixture | [Documentation](https://react.dev/reference/react/act) |
| `reitit` | clojure | 0.7 | native-adapter | [Documentation](https://github.com/metosin/reitit) |
| `ring` | clojure | 1 | native-adapter | [Documentation](https://github.com/ring-clojure/ring) |
| `rocket` | rust | 0.5 | native-adapter | [Documentation](https://rocket.rs/guide/v0.5/testing/) |
| `roda` | ruby | 3 | native-adapter | [Documentation](https://github.com/jeremyevans/roda) |
| `scrapy` | python | 2 | project-adapter | [Documentation](https://docs.scrapy.org/en/latest/topics/contracts.html) |
| `servant` | haskell | 0.20 | native-adapter | [Documentation](https://docs.servant.dev/en/latest/cookbook/testing/Testing.html) |
| `serverpod` | dart | 2, 3 | native-adapter | [Documentation](https://docs.serverpod.dev/concepts/testing/) |
| `shelf` | dart | 1 | native-adapter | [Documentation](https://pub.dev/packages/shelf) |
| `shiny` | r | 1 | native-adapter | [Documentation](https://shiny.posit.co/r/articles/improve/server-function-testing/) |
| `sinatra` | ruby | 3, 4 | native-adapter | [Documentation](https://sinatrarb.com/testing.html) |
| `slim` | php | 4 | native-adapter | [Documentation](https://github.com/slimphp/Slim/blob/4.x/composer.json) |
| `spock` | groovy | 2 | native-adapter | [Documentation](https://spockframework.org/spock/docs/2.3/all_in_one.html) |
| `spring-boot` | java | 3, 4 | native-adapter | [Documentation](https://docs.spring.io/spring-boot/system-requirements.html) |
| `starlette` | python | 0.46, 0.47 | project-adapter | [Documentation](https://www.starlette.io/testclient/) |
| `streamlit` | python | 1 | project-adapter | [Documentation](https://docs.streamlit.io/develop/api-reference/app-testing) |
| `svelte` | typescript, node | 4, 5 | tool-and-adapter | [Documentation](https://svelte.dev/docs/svelte/typescript) |
| `sveltekit` | typescript, node | 2 | tool-and-adapter | [Documentation](https://svelte.dev/docs/kit/cli) |
| `symfony` | php | 6.4, 7.4, 8.0 | native-adapter | [Documentation](https://laravel.com/framework/docs/pint) |
| `tornado` | python | 6 | project-adapter | [Documentation](https://www.tornadoweb.org/en/stable/testing.html) |
| `vapor` | swift | 4 | native-adapter | [Documentation](https://docs.vapor.codes/advanced/testing/) |
| `vitepress` | typescript, node | 1 | tool-and-adapter | [Documentation](https://vitepress.dev/reference/cli) |
| `vue` | typescript, node | 2, 3 | tool-fixture | [Documentation](https://eslint.vuejs.org/user-guide/) |
| `warp` | rust | 0.3, 0.4 | native-adapter | [Documentation](https://docs.rs/warp/latest/warp/test/index.html) |
| `yesod` | haskell | 1.6 | native-adapter | [Documentation](https://www.yesodweb.com/book/testing) |
| `yii` | php | 2 | native-adapter | [Documentation](https://www.yiiframework.com/doc/guide/2.0/en/test-overview) |

Django's default test runner is the framework's own runner. Its profile replaces
Python's generic test modes; it does not pretend coverage/mutation modes exist.
Select the existing project pytest setup explicitly when required. Deployment
security checks fail on warnings, so insecure development settings require a
separate correctly configured deployment-check environment.
Giraffe release lines refer to the Giraffe NuGet package, independently of the
.NET SDK: its default SDK is .NET 8, overridable with `options.dotnetSdk`.
ASP.NET Core release lines refer to the target .NET/ASP.NET Core release.

Vue and Svelte component architecture analysis reads script blocks, external
script imports and brace expressions while preserving source line numbers.
It remains source-text analysis: generated framework imports, template directive
semantics and build-time aliases require project rules/configuration or a
framework/compiler-aware analyzer.

## Runtime prerequisites and limits

| Ecosystems | Existing environment required by the adapter |
| :--- | :--- |
| Python | Project interpreter and test/plugin packages; `.venv/bin/python` or `DVT_PROJECT_PYTHON`. |
| Node | Installed project modules/compiler/test tools; matching Angular CLI, Vue type checker, Svelte checker or Astro checker when selected. |
| Ruby / PHP | Existing Bundler/Composer dependencies and configured test/analysis tools. |
| JVM | Project Maven/Gradle wrapper, explicit framework version and warmed offline dependencies. |
| Go / Rust | Selected module/lock graph; locked builds may fetch missing pinned artifacts but must not resolve a different graph. |
| .NET / Flutter | Restored project assets or existing pub environment; checks skip restore/resolution. |
| Clojure / Haskell / Erlang | Explicit Leiningen dependencies, Cabal freeze file or Rebar lock; required offline caches. |
| Crystal / Dart | Existing shards/pub lock and installed packages; no automatic package installation. |
| R / Julia / Perl | Existing project runtime and packages; R/Perl require explicit runtime environment variables. |
| C / C++ | Existing Conan/vcpkg version metadata and configured CMake build tree; no configure/fetch step. |
| Swift | Existing resolved packages and compatible platform/toolchain. |

Platform availability depends on Nixpkgs and the actual framework. Some profiles
require Linux or macOS tooling; evaluating a recipe on another system does not
prove an application runs there. Wisp/Lustre remain research entries because a
verified dependency-preserving execution path is not implemented. New release
lines and custom framework/plugin combinations need explicit validation.

Configured tools and test scripts can write their normal caches, generated
output or test databases. DVT does not sandbox arbitrary project scripts.
`style --check` uses a source copy while retaining access to installed plugins;
formatters must respect dependency directories and any custom paths they use.

## Research map for every language

Reviewed 16 November 2026 against primary framework/tool documentation. These
are representative framework families and relevant tools, not an exhaustive
list of every library. Candidate names in this map are **not** automatically
executable profiles; use `dvt list` for the implemented registry above. Where
there is no universal framework, language defaults remain the correct fallback.
The machine-readable map, including detailed compatibility constraints and
additional sources, is `lib/frameworks/coverage.json`.

| Language | Frameworks / ecosystems to account for | Tools / checks | Primary source |
| :--- | :--- | :--- | :--- |
| `ansible` | Molecule, Ansible collections | ansible-lint, yamlfmt, Molecule, ansible-test | [Documentation](https://docs.ansible.com/projects/molecule/installation/) |
| `assembly` | Project-specific / defaults | assembler diagnostics, project test harness | [Documentation](https://www.nasm.us/) |
| `bun` | Next.js, React, Vue, Nuxt, Angular, SvelteKit, NestJS, Hono | ESLint with framework plugins, Prettier with framework plugins, Vitest/Jest, Playwright, dependency-cruiser | [Documentation](https://nextjs.org/docs/app/api-reference/config/eslint) |
| `c-cpp` | Qt, Drogon, Catch2, GoogleTest | clang-tidy/Clazy, clang-format, CTest, Qt Test/DrogonTest | [Documentation](https://doc.qt.io/qtcreator/creator-preferences-analyzer-clang-tools.html) |
| `clojure` | Ring, Reitit, Pedestal | clj-kondo, cljfmt, clojure.test, Kaocha | [Documentation](https://cljdoc.org/d/clj-kondo/clj-kondo/2026.10.20/doc/running-on-the-jvm) |
| `crystal` | Kemal, Amber | Ameba, crystal tool format, crystal spec | [Documentation](https://amberframework.org/docs/v1.5/guides/testing) |
| `csharp` | ASP.NET Core, Giraffe | SDK analyzers, dotnet format/Fantomas, xUnit/NUnit/MSTest, NetArchTest | [Documentation](https://learn.microsoft.com/en-us/aspnet/core/testing/integration-testing) |
| `cue` | CUE modules | cue vet, cue fmt | [Documentation](https://cuelang.org/docs/reference/command/cue-help-vet/) |
| `dart` | Flutter, Serverpod | flutter analyze, dart format, flutter test, integration_test | [Documentation](https://docs.flutter.dev/reference/flutter-cli) |
| `deno` | Fresh, Hono | Deno quality/style/tests, Deno check, browser tests | [Documentation](https://fresh.deno.dev/docs/1.x/concepts/islands) |
| `dhall` | Dhall packages | Dhall type checking, dhall format, dhall lint | [Documentation](https://docs.dhall-lang.org/howtos/FAQ.html) |
| `docker` | Docker Compose, BuildKit | Hadolint, Buildx checks, Trivy, container-structure-test | [Documentation](https://docs.docker.com/build/checks/) |
| `elixir` | Phoenix, LiveView | mix format with HTMLFormatter, Credo, Sobelow, ExUnit, mix xref | [Documentation](https://phoenix.hexdocs.pm/testing.html) |
| `elm` | elm-ui, Lamdera | elm-format, elm-review, elm-test | [Documentation](https://package.elm-lang.org/packages/jfmengels/elm-review/latest/) |
| `empty` | Project-specific / defaults | shared repository checks | [Documentation](https://wiki.nixos.org/wiki/Flakes/en) |
| `erlang` | Cowboy, OTP | erlfmt, Dialyzer, EUnit, Common Test, rebar3 xref | [Documentation](https://rebar3.org/docs/testing/) |
| `fortran` | fpm, pFUnit, test-drive | compiler diagnostics, fprettify, fpm test, pFUnit | [Documentation](https://fpm.fortran-lang.org/spec/features.html) |
| `fsharp` | ASP.NET Core, Giraffe | SDK analyzers, dotnet format/Fantomas, xUnit/NUnit/MSTest, NetArchTest | [Documentation](https://learn.microsoft.com/en-us/aspnet/core/testing/integration-testing) |
| `github-actions` | GitHub Actions | actionlint, zizmor, yamllint | [Documentation](https://docs.zizmor.sh/integrations/) |
| `gleam` | Wisp, Lustre | gleam check, gleam format, gleeunit | [Documentation](https://gleeunit.hexdocs.pm/index.html) |
| `go` | Gin, Echo, Fiber | golangci-lint, gofumpt, gosec, govulncheck, go test/httptest | [Documentation](https://gin-gonic.com/en/docs/testing/) |
| `graphql` | GraphQL server/client frameworks | GraphQL ESLint, Prettier, GraphQL Inspector, resolver tests | [Documentation](https://the-guild.dev/graphql/inspector/docs) |
| `groovy` | Grails, Spock | CodeNarc, Spock, Gradle tests, ArchUnit | [Documentation](https://spockframework.org/spock/docs/2.5/all_in_one.html) |
| `hashi` | OpenTofu modules, Terraform modules, Packer, Nomad | TFLint, Checkov, tofu/terraform fmt, native tests, packer validate | [Documentation](https://opentofu.org/docs/cli/commands/test/) |
| `haskell` | Yesod, Servant, IHP | HLint, Ormolu, Hspec, yesod-test, Weeder | [Documentation](https://www.yesodweb.com/blog/2013/05/yesod-1-2-released) |
| `haxe` | Heaps, OpenFL, Lime | Haxe compiler diagnostics, formatter, utest/MUnit | [Documentation](https://heaps.io/documentation/installation.html) |
| `hdl` | cocotb, VUnit, UVM | Verilator, Verible, GHDL, cocotb/VUnit tests | [Documentation](https://docs.cocotb.org/en/development/simulator_support.html) |
| `java` | Spring Boot, Quarkus, Micronaut | Checkstyle, PMD, SpotBugs, JUnit, ArchUnit | [Documentation](https://docs.spring.io/spring-boot/system-requirements.html) |
| `julia` | Genie, SciML | JuliaFormatter, Aqua, JET, Pkg.test | [Documentation](https://pkgdocs.julialang.org/v1.2/api/) |
| `jupyter` | Jupyter, nbval, Papermill | Ruff, nbstripout, nbval | [Documentation](https://nbval.readthedocs.io/en/latest/) |
| `kotlin` | Ktor, Spring Boot, Compose | ktlint, detekt, JUnit/kotlin.test, ArchUnit | [Documentation](https://ktor.io/docs/server-testing.html) |
| `kubernetes` | Helm, Kustomize | helm lint, kubeconform, helm-unittest, policy checks | [Documentation](https://helm.sh/docs/v2/helm/helm_lint/) |
| `latex` | LaTeX packages, l3build | ChkTeX, latexindent, l3build | [Documentation](https://tug.ctan.org/macros/latex/contrib/l3build/l3build.pdf) |
| `lean4` | Mathlib, Lake | Lake build, Lake lint, Lake test | [Documentation](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Lake/) |
| `lua` | LÖVE, Lapis, OpenResty | Luacheck/Selene, StyLua, Busted | [Documentation](https://lunarmodules.github.io/busted/) |
| `markdown` | Docusaurus, MkDocs, VitePress | markdownlint, Vale, Prettier, link/build checks | [Documentation](https://docusaurus.io/tests/pages) |
| `nickel` | Nickel contracts | Nickel type checking, Nickel format, contract evaluation | [Documentation](https://nickel-lang.org/user-manual/typing/) |
| `nim` | Jester, Prologue | nph/nimpretty, nim check, unittest/Testament | [Documentation](https://nim-lang.org/1.4.2/tools.html) |
| `nix` | NixOS, Home Manager, flake-parts | Statix, deadnix, nixfmt, flake checks, NixOS VM tests | [Documentation](https://wiki.nixos.org/wiki/Flakes/en) |
| `node` | Next.js, React, Vue, Nuxt, Angular, SvelteKit, NestJS, Hono | ESLint with framework plugins, Prettier with framework plugins, Vitest/Jest, Playwright, dependency-cruiser | [Documentation](https://nextjs.org/docs/app/api-reference/config/eslint) |
| `ocaml` | Dream, Opium, Eliom | ocamlformat, Dune tests, Alcotest, Bisect_ppx | [Documentation](https://github.com/camlworks/dream) |
| `odin` | Odin core testing, Raylib integrations | odin check/vet, odin test | [Documentation](https://odin-lang.org/docs/overview/) |
| `opa` | Rego, Conftest | Regal, opa fmt, opa test, Conftest | [Documentation](https://www.openpolicyagent.org/ecosystem/by-feature/policy-testing) |
| `perl` | Mojolicious, Dancer2, Catalyst | Perl::Critic, Perl::Tidy, prove/Test::Mojo | [Documentation](https://docs.mojolicious.org/Mojolicious/Guides/Testing) |
| `php` | Laravel, Symfony | Pint, PHPStan/Larastan, Psalm, PHPUnit/Pest, Deptrac | [Documentation](https://laravel.com/framework/docs/pint) |
| `platformio` | Arduino, ESP-IDF, Zephyr, Unity | PlatformIO check, clang-format, pio test | [Documentation](https://docs.platformio.org/en/stable/advanced/unit-testing/frameworks/index.html) |
| `powershell` | Pester, PSRule | PSScriptAnalyzer, Pester | [Documentation](https://pester.dev/docs/v5/introduction/installation) |
| `presenterm` | Presenterm | markdownlint, Vale, presentation rendering | [Documentation](https://mfontanini.github.io/presenterm/features/introduction.html) |
| `protobuf` | Buf, gRPC | buf lint, buf format, buf breaking | [Documentation](https://buf.build/docs/lint/) |
| `pulumi` | Pulumi SDKs | language-native checks, Pulumi mocks, policy checks | [Documentation](https://www.pulumi.com/docs/iac/guides/testing/unit/) |
| `purescript` | Halogen, Spork | purs-tidy, Spago tests, purescript-spec | [Documentation](https://pursuit.purescript.org/packages/purescript-halogen/7.1.0) |
| `python` | Django, Flask, FastAPI | Ruff, djLint, Bandit, pytest, import-linter | [Documentation](https://docs.djangoproject.com/en/5.2/ref/django-admin/) |
| `qml` | Qt Quick | qmllint, qmlformat, Qt Quick Test | [Documentation](https://doc.qt.io/qt-6/qtqml-tooling-qmllint.html) |
| `r` | Shiny, Plumber | lintr, styler, testthat, shinytest2 | [Documentation](https://shiny.posit.co/r/articles/improve/shinytest2/) |
| `racket` | Racket web-server, RackUnit | raco make, raco test, RackUnit | [Documentation](https://docs.racket-lang.org/rackunit/) |
| `ruby` | Rails, Sinatra, Hanami | RuboCop Rails, Brakeman, Minitest/RSpec, Packwerk | [Documentation](https://guides.rubyonrails.org/command_line.html) |
| `rust` | Axum, Actix Web, Rocket, Bevy | Clippy, rustfmt, cargo-audit, cargo-deny, cargo test/nextest | [Documentation](https://actix.rs/docs/testing/) |
| `scala` | Play, http4s, ZIO | scalafmt, Scalafix, ScalaTest/specs2, sbt dependency checks | [Documentation](https://www.playframework.com/documentation/3.0.x/ScalaTestingWithScalaTest) |
| `shell` | Bats, ShellSpec | ShellCheck, shfmt, Bats | [Documentation](https://bats-core.readthedocs.io/en/stable/faq.html) |
| `solidity` | Foundry, Hardhat | Slither, forge fmt, forge test, fuzz/invariant tests | [Documentation](https://www.getfoundry.sh/forge/index.html) |
| `sql` | dbt, SQLMesh, pgTAP | SQLFluff, sqruff, dbt tests, schema assertions | [Documentation](https://docs.sqlfluff.com/en/stable/configuration/templating/dbt.html) |
| `swi-prolog` | SWI HTTP, PlUnit | load checks, PlUnit | [Documentation](https://www.swi-prolog.org/pldoc/man?section=pldoc-running) |
| `swift` | Vapor, SwiftUI | SwiftLint, SwiftFormat, swift test, VaporTesting/XCTVapor | [Documentation](https://docs.vapor.codes/advanced/testing/) |
| `terraform` | OpenTofu modules, Terraform modules, Packer, Nomad | TFLint, Checkov, tofu/terraform fmt, native tests, packer validate | [Documentation](https://opentofu.org/docs/cli/commands/test/) |
| `typescript` | Next.js, React, Vue, Nuxt, Angular, SvelteKit, NestJS, Hono | ESLint with framework plugins, Prettier with framework plugins, Vitest/Jest, Playwright, dependency-cruiser | [Documentation](https://nextjs.org/docs/app/api-reference/config/eslint) |
| `typst` | Typst packages | Tinymist, Typstyle, Typst compilation | [Documentation](https://typst.app/open-source/) |
| `vlang` | veb, V testing | v vet, v fmt, v test | [Documentation](https://docs.vlang.io/tools.html) |
| `web` | Next.js, React, Vue, Nuxt, Angular, SvelteKit, NestJS, Hono | ESLint with framework plugins, Prettier with framework plugins, Vitest/Jest, Playwright, dependency-cruiser | [Documentation](https://nextjs.org/docs/app/api-reference/config/eslint) |
| `zig` | Zig build system, zls integrations | zig fmt, zig build test | [Documentation](https://ziglang.org/learn/getting-started/) |

Tool locks do not freeze external vulnerability databases or the existing
language security commands' remote Semgrep auto rules. Those sources can change
findings independently of installed tools; reproducing those findings requires
pinning their data/rule sources as well.

## Maintaining profiles

Add metadata to `lib/frameworks/registry.json`, a version-aware module or recipe,
source links and a compatibility fixture. Keep the all-language coverage map
in sync. Framework plugin bundles belong under `lib/frameworks/bundles/`, never
under a sample application's dependencies. Update their locks and Nix hashes
together, then run the relevant framework checks and `nix flake check`.

The command interface everywhere is `quality`, `style`, `security`,
`architecture` and `tests`; use `style --check` in CI. Framework profiles extend
this interface rather than introducing competing top-level commands.
