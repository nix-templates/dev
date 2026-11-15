# dev

[![check](https://github.com/nix-templates/dev/actions/workflows/check.yml/badge.svg)](https://github.com/nix-templates/dev/actions/workflows/check.yml)

A Nix dev shell for your language, with the tools already in it.

Run `nix develop` and you have the compiler, the language server, the linters,
the formatter, the security scanners and the test tools. There are 68 language
templates, and all of them answer to the same five commands:

| Command | What it runs |
| :--- | :--- |
| `lint` | Every linter and static analyser for your languages. |
| `fmt` | Every formatter. `fmt --check` reports and changes nothing. |
| `scan` | Leaked secrets, vulnerable dependencies, SAST. |
| `layers` | Your architecture rules: which code may use which, and what must stay pure. |
| `tests` | Your tests. `tests --coverage` and `tests --mutation` where the language has a tool for it. |

The terminal, VS Code and Neovim all call these same five, so your editor and
your CI never disagree about what "clean" means.

## Quick start

```shell
nix flake init -t github:nix-templates/dev#rust
direnv allow        # or: nix develop
```

Pick any name from the [tables below](#templates).

You get a short `flake.nix` that names your language. The tool list itself
stays here, in [`lib/languages/`](./lib/languages/). That is on purpose:
`nix flake update dev` hands you every tool that gets added later, and you
never copy a new version of a template by hand.

A project in several languages lists several names:

```nix
languages = [ "rust" "python" "nix" ];
```

One shell, three toolsets, and each command covers all three.

Don't like what a language brings? Copy its file from `lib/languages/` next to
your flake, edit it, and list the path instead of the name:
`languages = [ ./rust.nix ]`.

## Tools wait for their config

Most tools only run when your project has their config file. No `deny.toml`,
no cargo-deny. No `.go-arch-lint.yml`, no go-arch-lint. A new project starts
quiet and gets stricter as you add config.

Every project gets `typos`, `editorconfig-checker` and `gitleaks` regardless.

A command says what it left out. Every tool it skips gets a line,
`:: skipping cargo-deny (no deny.toml here)`. And when nothing at all ran for
one of your languages, you get `:: checked nothing: tests for python`.

## Architecture rules

`layers` reads `architecture.toml` and fails when code breaks it.

```toml
version = 1

[[layer]]
name = "core"
paths = ["src/core"]
pure = true

[[layer]]
name = "adapters"
paths = ["src/adapters"]
may_use = ["core"]

[[layer]]
name = "app"
paths = ["src"]
may_use = ["core", "adapters"]
```

Two rules, and that is all of it:

- **Layers.** A file may use its own layer and the layers its layer names.
- **Purity.** A `pure` layer is a functional core. Same input, same output, and
  nothing outside the function changes. So no files, network, clock,
  environment, randomness, threads or shared state in there.

Test files sit outside the layers. They are not checked, and code in a layer
may not use them.

A failure tells you where, why, and what to do about it:

```text
core/plan.py:2: layer: 'core' may not use 'adapters': adapters.disk is adapters/disk.py
    fix: 'core' may use no other layer. Move what both need into a layer 'core' may use,
    or define the interface in 'core' and implement it in 'adapters'.
```

That last line is written for coding agents as much as for people. An agent
that hits it gets told how to fix the design, which beats it papering over
the error.

### Old code

Existing code won't pass new rules on day one. So:

```shell
layers --explain   # which file landed in which layer
layers --accept    # write today's violations to architecture-baseline.json
```

After that, known violations pass and new ones fail. The baseline can only
shrink. Fix a violation and `layers` fails until `layers --prune` takes it
off the list.

In CI, run `layers --since origin/main`. It also fails when someone grew the
baseline, or made the check pass by loosening the rules: dropping `pure`,
widening `may_use`, excluding the file, or moving it to a layer that asks
less. Rules may only get stricter. `--allow-weaker` is for the one change
where loosening them was agreed.

### What it reads

55 languages. `layers --languages` lists them with their file types.

| How a file names what it uses | Languages |
| :--- | :--- |
| A reader of its own | Rust (crate dependencies from every `Cargo.toml`, then `use` paths), Python (the syntax tree, notebooks included), JavaScript and TypeScript, C and C++ |
| A declared package or module | Java, Kotlin, Groovy, Scala, C#, F#, PHP, Haxe, Perl, Elixir, Erlang, Haskell, PureScript, Elm, Clojure, Fortran, Rego, VHDL |
| A path to a file or directory | Go, CUE, Dart, Lua, Nim, Crystal, Zig, V, Odin, Gleam, Lean, Racket, Julia, R, Nix, Dhall, Nickel, shell, PowerShell, Protobuf, GraphQL, Solidity, Terraform, QML, CMake, Typst, LaTeX, Prolog, Verilog, assembly |
| A convention | Swift (a target is a directory under `Sources/`), OCaml (a file is a module, a dune library is a directory), Ruby (`require`, and constants the way Zeitwerk maps them to files) |

What counts as impure differs per language: `java.io` and
`System.currentTimeMillis()` in Java, `os` and goroutines in Go, `IO` in a
type signature in Haskell. The lists are in
[`languages.py`](./lib/layers/layers/languages.py) and
[`effects.py`](./lib/layers/layers/effects.py).

It reads source text, not the compiler's view. That makes it close, not
exact: macros, names built at run time and build-system path mappings are
invisible to it. When it guesses your import roots wrong, set them with
`[sources] roots`. A file it cannot parse fails the check. It never passes
unread. In a git checkout it reads what git tracks or would add, so whatever
`.gitignore` leaves out stays out. A script with no file extension is read as
the language its `#!` line names.

Some languages have a real architecture tool of their own. `layers` runs it
after the rules, when you have its config: go-arch-lint, `cargo deny check
bans`, deptry and import-linter, dependency-cruiser and knip, the Maven
enforcer, Gradle's `buildHealth`, sbt-explicit-dependencies, `mix xref`,
`rebar3 xref`, deptrac, packwerk, weeder, `dependency_validator`, periphery
and `buf breaking`.

More settings: `strict = true` fails on files in no layer, `exclude` skips
paths, `forbid_external` keeps packages out of a layer, `hint` adds your own
advice to a layer's failures, and `[purity] allow` and `forbid` adjust what
counts as pure. `apart = true` on a layer keeps the entries under its `paths`
apart, which is how you say that apps or plugins do not use each other.

## In your own flake

The templates are a thin layer over one function. Call it yourself:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    dev.url = "github:nix-templates/dev";
    dev.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    { self, nixpkgs, dev }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      project = dev.lib.mkProject {
        inherit pkgs;
        languages = [ "rust" "python" ];
        src = self;
      };
    in
    {
      devShells.x86_64-linux.default = project.devShell;
      checks.x86_64-linux = project.checks;
    };
}
```

The tools are built from the `pkgs` you pass in, so they match what your
project builds with.

| Argument | What it is |
| :--- | :--- |
| `pkgs` | Your package set. The only required one. |
| `languages` | Names, paths to your own language files, or both. |
| `src` | Your source tree, `self` in a flake. Turns on `checks`, which needs an `architecture.toml`. |
| `rustToolchain` | Your pinned Rust toolchain. Clippy changes its lints every release, so pin it. |
| `python` | Another Python interpreter. |
| `extraTools` | More packages for the shell. |
| `options.pythonVenv` | `true` makes and activates a `.venv` when you enter the shell. |

It returns `devShell`, the pieces for a shell of your own (`packages`,
`tools`, `env`), the five `commands` as packages for CI, and `checks`.
The [`project`](./project/) template is this, for every system, with a
starting `architecture.toml`.

## In CI

One command runs any of the five on a checkout:

```shell
nix run --no-write-lock-file github:nix-templates/dev#ci -- lint
```

A project with a flake of its own, where `lint` is in the default dev shell,
runs it there. Your `flake.lock` decides the tools, same as on your machine.
A project without one gets a dev shell made on the spot: `ci` reads the files
git tracks, works out the languages and asks `mkProject` for them.
`ci --languages` shows what it found.

CI is stricter than your terminal in two places. `fmt` is `fmt --check`,
because CI never rewrites your files. And `layers` fails when there is no
`architecture.toml`: a check with nothing to check should not go green. A
project with nothing to keep apart says so with one layer, `paths = ["."]`.

It exits 0 when the check passed, 1 when it found something and 2 when it
could not run. Arguments go to the command: `ci layers --since origin/main`.

A GitLab job, five times over:

```yaml
check:
  image: nixos/nix
  variables:
    NIX_CONFIG: experimental-features = nix-command flakes
  parallel:
    matrix:
      - COMMAND: [fmt, scan, lint, layers, tests]
  script:
    - nix run --no-write-lock-file github:nix-templates/dev#ci -- $COMMAND
```

A GitHub Actions step:

```yaml
- uses: DeterminateSystems/nix-installer-action@main
- run: nix run --no-write-lock-file github:nix-templates/dev#ci -- lint
```

### Pin it

This repository has no lock file and follows unstable nixpkgs, so the line
above can bring newer tools tomorrow. A project with its own flake does not
care: its tools come from its own lock. For any other, name both revisions:

```shell
nix run \
  --override-input nixpkgs github:NixOS/nixpkgs/<revision> \
  github:nix-templates/dev/<revision>#ci -- lint
```

Take the nixpkgs revision from `nixos-unstable`. The tool lists here follow
it, and a release branch can lack a tool, in which case no dev shell can be
made and `ci` exits 2.

The first line of a run says what it used:

```text
ci: lint in a dev shell made for nix, shell by nix-templates/dev 4c1d329e9187 with nixpkgs d5cc68339997
```

Asking Nix for a dev shell takes seconds, so `ci` asks once and keeps the
shell's script in `~/.cache/nix-templates-dev`. The other four commands of a
pipeline then start in a fraction of a second, as long as the jobs share that
directory. `XDG_CACHE_HOME` moves it. The kept script is run as it is, so
share the directory only between jobs that may run each other's code.

### Green means checked

A run that passed without checking anything says so:

```text
ci: checked nothing (language): tests ran nothing for python
```

| Case | What happened |
| :--- | :--- |
| `no-languages` | None of the languages here was found, so only `typos`, `editorconfig-checker` and `gitleaks` ran. |
| `no-tool` | The command ran no tool at all. |
| `language` | A language has tools for this command and none of them ran. Python without tests, say. |
| `no-layer-files` | `layers` read files and `architecture.toml` puts none of them in a layer. |
| `no-comparison` | The revision you gave `--since` has no `architecture.toml`. |
| `own-command` | The command is the project's own program, not one from here. |

`ci --strict tests` fails on any of them. `ci --strict=language,no-tool tests`
fails on the ones you name.

## For coding agents

There is an MCP server. It lets an agent look up what the library has and
write the flake for the project it is working on.

```json
{
  "mcpServers": {
    "nix-dev": {
      "command": "nix",
      "args": ["run", "github:nix-templates/dev#mcp"]
    }
  }
}
```

| Tool | What it does |
| :--- | :--- |
| `list_languages` | Every language, with its test modes, whether `layers` reads it, and whether it has an architecture tool of its own. |
| `describe_language` | Every tool in one language's shell, and exactly what each command runs. |
| `generate_flake` | The `flake.nix` and `.envrc` for the languages you name. |
| `architecture_rules` | An `architecture.toml` from a list of layers, checked by the real parser. |

It writes nothing to disk. It hands back file contents and the agent decides.

## Templates

A tick under `layers` means it reads that template's sources, so your
`architecture.toml` applies to them. `+ tool` means the language also has an
architecture tool of its own, which runs after the rules. `tests` lists the
extra modes next to plain `tests`.

### Systems and application languages

| Template | In the shell | `layers` | `tests` |
| :--- | :--- | :--- | :--- |
| [`c-cpp`](./c-cpp/) | `cmake`, `ninja`, `meson`, `bear`, `gtest`, `lcov`, `doxygen`, ... | ✓ | ✓ |
| [`crystal`](./crystal/) | `crystal`, `shards`, `crystalline`, `ameba` | ✓ | ✓ |
| [`csharp`](./csharp/) | `dotnet-sdk`, `msbuild`, `mono`, `omnisharp-roslyn`, `csharpier`, `netcoredbg` | ✓ | ✓ coverage, mutation |
| [`dart`](./dart/) | `dart`, `flutter` | ✓ + tool | ✓ coverage |
| [`fortran`](./fortran/) | `gfortran`, `fpm`, `fortls`, `fprettify` | ✓ | ✓ |
| [`fsharp`](./fsharp/) | `dotnet-sdk`, `msbuild`, `fsautocomplete`, `fantomas` | ✓ | ✓ coverage, mutation |
| [`go`](./go/) | `go`, `gotools`, `gotestsum`, `delve`, `gopls`, `golangci-lint`, `go-tools`, ... | ✓ + tool | ✓ coverage, bench |
| [`haxe`](./haxe/) | `haxe`, `neko` | ✓ |  |
| [`java`](./java/) | `openjdk`, `maven`, `gradle`, `jdt-language-server`, `checkstyle`, `pmd`, `google-java-format`, ... | ✓ + tool | ✓ coverage, mutation |
| [`julia`](./julia/) | `julia`, `pandoc-cli` | ✓ | ✓ coverage |
| [`kotlin`](./kotlin/) | `kotlin`, `gradle`, `openjdk`, `kotlin-language-server`, `ktlint`, `detekt`, `ktfmt`, ... | ✓ + tool | ✓ coverage, mutation |
| [`nim`](./nim/) | `x86_64-unknown-linux-gnu-nim`, `nimble`, `nimlangserver`, `nph` | ✓ | ✓ |
| [`odin`](./odin/) | `odin`, `ols` | ✓ | ✓ |
| [`perl`](./perl/) | `perl`, `perlnavigator`, `PLS`, `Perl-Critic`, `Perl-Tidy` | ✓ | ✓ |
| [`php`](./php/) | `php-with-extensions`, `composer`, `phpactor`, `phpstan`, `psalm`, `php-codesniffer`, `php-cs-fixer`, ... | ✓ + tool | ✓ mutation |
| [`python`](./python/) | `python3`, `uv`, `basedpyright`, `ruff`, `mypy`, `vulture`, `bandit`, ... | ✓ + tool | ✓ coverage, mutation |
| [`racket`](./racket/) | `racket` | ✓ | ✓ |
| [`ruby`](./ruby/) | `ruby`, `ruby-lsp`, `solargraph`, `rubocop`, `bundler-audit` | ✓ + tool | ✓ |
| [`rust`](./rust/) | `cargo`, `rustc`, `clippy`, `rustfmt`, `cargo-edit`, `cargo-watch`, `cargo-nextest`, ... | ✓ + tool | ✓ coverage, mutation, bench |
| [`scala`](./scala/) | `scala`, `sbt`, `scala-cli`, `mill`, `coursier`, `openjdk`, `metals`, ... | ✓ + tool | ✓ coverage, mutation |
| [`swift`](./swift/) | `swift`, `sourcekit-lsp`, `swiftlint`, `swiftformat` | ✓ + tool | ✓ coverage |
| [`vlang`](./vlang/) | `vlang` | ✓ | ✓ |
| [`zig`](./zig/) | `zig`, `zls`, `lldb` | ✓ | ✓ |
| `qml` (library only) | `qtdeclarative` | ✓ |  |

### Functional languages

| Template | In the shell | `layers` | `tests` |
| :--- | :--- | :--- | :--- |
| [`clojure`](./clojure/) | `clojure`, `leiningen`, `boot`, `babashka`, `clojure-lsp`, `clj-kondo`, `cljfmt`, ... | ✓ | ✓ coverage |
| [`elixir`](./elixir/) | `elixir`, `git`, `elixir-ls`, `nodejs`, `inotify-tools`, `libnotify`, `gigalixir` | ✓ + tool | ✓ coverage |
| [`elm`](./elm/) | `elm`, `elm-json`, `elm2nix`, `elm-language-server`, `elm-review`, `elm-test`, `elm-format`, ... | ✓ | ✓ |
| [`erlang`](./erlang/) | `erlang`, `rebar3`, `erlang-language-platform`, `erlfmt` | ✓ + tool | ✓ coverage |
| [`gleam`](./gleam/) | `gleam`, `erlang`, `rebar3`, `nodejs` | ✓ | ✓ |
| [`haskell`](./haskell/) | `ghc`, `cabal-install`, `stack`, `hoogle`, `haskell-language-server`, `hlint`, `ormolu`, ... | ✓ + tool | ✓ coverage, bench |
| [`lean4`](./lean4/) | `lean4` | ✓ | ✓ |
| [`ocaml`](./ocaml/) | `ocaml`, `opam`, `dune`, `utop`, `odoc`, `ocaml-lsp-server`, `ocamlformat` | ✓ | ✓ coverage |
| [`purescript`](./purescript/) | `purescript`, `spago-legacy`, `nodejs`, `esbuild` | ✓ | ✓ |

### JavaScript and the web

| Template | In the shell | `layers` | `tests` |
| :--- | :--- | :--- | :--- |
| [`bun`](./bun/) | `bun`, `nodejs`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `biome`, `oxlint`, ... | ✓ + tool | ✓ coverage, mutation, browser |
| [`deno`](./deno/) | `deno` | ✓ | ✓ coverage, bench |
| [`graphql`](./graphql/) | `nodejs`, `pnpm`, `typescript`, `graphql-language-service-cli`, `typescript-language-server`, `eslint`, `biome`, ... | ✓ + tool | ✓ coverage, mutation, browser |
| [`node`](./node/) | `nodejs`, `pnpm`, `yarn`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `eslint`, ... | ✓ + tool | ✓ coverage, mutation, browser |
| [`typescript`](./typescript/) | `nodejs`, `pnpm`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `biome`, `eslint`, ... | ✓ + tool | ✓ coverage, mutation, browser |
| [`web`](./web/) | `nodejs`, `pnpm`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `tailwindcss-language-server`, `emmet-language-server`, ... | ✓ + tool | ✓ coverage, mutation, browser |

### Scripting and glue

| Template | In the shell | `layers` | `tests` |
| :--- | :--- | :--- | :--- |
| [`assembly`](./assembly/) | `nasm`, `yasm`, `binutils`, `asm-lsp`, `radare2`, `lldb`, `gdb` | ✓ |  |
| [`groovy`](./groovy/) | `groovy`, `gradle`, `openjdk`, `groovy-language-server`, `npm-groovy-lint` | ✓ + tool | ✓ coverage |
| [`lua`](./lua/) | `lua`, `luajit`, `lua-language-server`, `selene`, `luacheck`, `stylua`, `busted` | ✓ | ✓ |
| [`powershell`](./powershell/) | `powershell`, `powershell-editor-services` | ✓ | ✓ |
| [`shell`](./shell/) | `bash-interactive`, `bats`, `bash-language-server`, `ShellCheck`, `shfmt`, `shellspec` | ✓ | ✓ |
| [`swi-prolog`](./swi-prolog/) | `swi-prolog` | ✓ |  |

### Configuration and policy languages

| Template | In the shell | `layers` | `tests` |
| :--- | :--- | :--- | :--- |
| [`cue`](./cue/) | `cue`, `cuelsp` | ✓ | ✓ |
| [`dhall`](./dhall/) | `dhall`, `dhall-json`, `dhall-bash`, `dhall-docs`, `dhall-nix`, `dhall-lsp-server` | ✓ |  |
| [`nickel`](./nickel/) | `nickel`, `nls` | ✓ |  |
| [`nix`](./nix/) | `nixd`, `statix`, `deadnix`, `nixfmt`, `vulnix`, `nix-tree`, `nix-diff`, ... | ✓ | ✓ |
| [`opa`](./opa/) | `open-policy-agent`, `conftest`, `regal` | ✓ | ✓ |
| [`protobuf`](./protobuf/) | `protobuf`, `buf`, `grpcurl`, `protolint` | ✓ + tool |  |

### Infrastructure and operations

| Template | In the shell | `layers` | `tests` |
| :--- | :--- | :--- | :--- |
| [`ansible`](./ansible/) | `ansible-core`, `sshpass`, `ansible-language-server`, `yaml-language-server`, `ansible-lint`, `yamllint`, `yamlfmt`, ... |  | ✓ |
| [`docker`](./docker/) | `docker-compose`, `docker-buildx`, `podman`, `buildah`, `skopeo`, `dive`, `dockerfile-language-server`, ... |  |  |
| [`github-actions`](./github-actions/) | `act`, `gh`, `yaml-language-server`, `actionlint`, `yamllint`, `yamlfmt`, `zizmor`, ... |  |  |
| [`hashi`](./hashi/) | `terraform`, `vault`, `nomad`, `consul`, `packer`, `terragrunt`, `nomad-autoscaler`, ... | ✓ | ✓ |
| [`kubernetes`](./kubernetes/) | `kubectl`, `kubernetes-helm`, `kustomize`, `kubectx`, `k9s`, `stern`, `yaml-language-server`, ... |  | ✓ |
| [`pulumi`](./pulumi/) | `pulumi`, `python3`, `go`, `nodejs`, `openjdk`, `maven`, `gopls`, ... | ✓ |  |
| [`terraform`](./terraform/) | `opentofu`, `terragrunt`, `terraform-ls`, `tflint`, `terraform-docs`, `tfsec`, `checkov`, ... | ✓ | ✓ |

### Data, hardware and documents

| Template | In the shell | `layers` | `tests` |
| :--- | :--- | :--- | :--- |
| [`hdl`](./hdl/) | `verilator`, `iverilog`, `ghdl-mcode`, `gtkwave`, `verible`, `svls`, `sby`, ... | ✓ | ✓ |
| [`jupyter`](./jupyter/) | `python3`, `poetry`, `uv`, `basedpyright`, `ruff`, `mypy`, `nbstripout`, ... | ✓ | ✓ |
| [`latex`](./latex/) | `texlive-combined-full`, `tectonic`, `texlab`, `vale`, `pandoc-cli` | ✓ |  |
| [`markdown`](./markdown/) | `marksman`, `harper`, `markdownlint-cli2`, `vale`, `lychee`, `mdformat`, `prettier`, ... |  |  |
| [`platformio`](./platformio/) | `platformio`, `cmake`, `ninja`, `bear`, `clang-tools`, `cppcheck`, `codespell`, ... | ✓ | ✓ |
| [`presenterm`](./presenterm/) | `presenterm`, `mermaid-cli`, `typst`, `pandoc-cli`, `marksman`, `harper`, `markdownlint-cli2`, ... |  |  |
| [`r`](./r/) | `R`, `pandoc-cli`, `texlive-combined-full` | ✓ | ✓ coverage |
| [`solidity`](./solidity/) | `solc`, `solc-select`, `foundry`, `nodejs`, `pnpm`, `slither-analyzer` | ✓ | ✓ coverage, bench |
| [`sql`](./sql/) | `postgresql`, `sqlite`, `pgcli`, `usql`, `sqls`, `sqlfluff`, `sqruff`, ... |  |  |
| [`typst`](./typst/) | `typst`, `tinymist`, `typstyle`, `vale`, `pandoc-cli` | ✓ |  |

### Starting point

| Template | In the shell | `layers` | `tests` |
| :--- | :--- | :--- | :--- |
| [`empty`](./empty/) | `treefmt`, `dprint`, `taplo`, `yamlfmt`, `yamllint`, `markdownlint-cli2`, `actionlint` |  |  |
| [`project`](./project/) | For several languages at once: you list them in `flake.nix`. Comes with an `architecture.toml`. |  |  |

## Editors

Every language template comes with `.envrc`, `.vscode/` and `.nvim.lua`.

**VS Code.** Install the [direnv extension][direnv-ext]. It loads the shell into
the editor so extensions find the binaries, and the five commands show up as
tasks.

```shell
code --install-extension mkhl.direnv
```

**Neovim.** `.nvim.lua` is project-local config, which Neovim reads when
`exrc` is on:

```lua
vim.o.exrc = true
```

Answer `:trust` the first time. You get LSP through the built-in
`vim.lsp.config` (Neovim 0.11+, no plugins), format on save, and
`:DevLint`, `:DevFmt`, `:DevScan`, `:DevLayers` and `:DevTests`.

**Anything else.** Start it from a directory where direnv is active and it
inherits the whole toolchain through `PATH`.

## Notes on individual templates

- **`elixir`**: `mix credo` and `mix deps.audit` are Hex dependencies; add :credo and :mix_audit to mix.exs.
- **`haxe`**: The Haxe language server ships with the vshaxe VS Code extension rather than as a standalone nixpkgs package.
- **`julia`**: LanguageServer.jl and JuliaFormatter.jl are Julia packages rather than nixpkgs ones: `julia -e 'using Pkg; Pkg.add(["LanguageServer", "JuliaFormatter"])'`.
- **`purescript`**: purescript-language-server and purs-tidy are not packaged in nixpkgs; `npm i -D purescript-language-server purs-tidy` and the .envrc puts them on PATH.
- **`racket`**: racket-langserver is distributed through raco: `raco pkg install racket-langserver`.
- **`ruby`**: Brakeman, the usual Rails SAST tool, is marked unfree in nixpkgs; add it with `config.allowUnfree = true` if you need it.
- **`solidity`**: No Solidity language server is packaged in nixpkgs; `npm i -D @nomicfoundation/solidity-language-server solhint` and the .envrc picks them up.
- **`swi-prolog`**: The LSP entry expects `pack_install(lsp_server)` inside SWI-Prolog; it is skipped automatically when the pack is missing.
- **`terraform`**: Terraform itself is BUSL-licensed and therefore unfree in nixpkgs; this template uses OpenTofu. See the `hashi` template if you need the HashiCorp binaries.
- **`vlang`**: v-analyzer, the V language server, is not packaged in nixpkgs; install it with `v install`.
- **Aliases**: `c` and `cpp` for `c-cpp`; `gha` for `github-actions`; `k8s` for `kubernetes`; `docs` and `md` for `markdown`; `js` for `node`; `sh` for `shell`; `tf` for `terraform`; `ts` for `typescript`

## Working on this repository

```shell
nix develop           # or direnv allow
check                 # evaluate every template, on every system
build                 # build every template's shell
format                # nixfmt every .nix file
nix flake check       # the tests of layers, ci and the MCP server, shellcheck on every command
```

| Path | What it is |
| :--- | :--- |
| `lib/languages/` | One file per language: its tools and its part of each command. |
| `lib/default.nix` | `mkProject`, which puts languages together. |
| `lib/helpers.sh` | The shell helpers the commands share (`run`, `when`, `run_on`, ...). |
| `lib/layers/` | `layers`, in Python with no dependencies, and its tests. |
| `lib/ci/` | `ci`, same. |
| `mcp/` | The MCP server, same. |
| `<name>/` | A template: a flake that names its language, plus editor files. |

To add a language, add `lib/languages/<name>.nix` and a template folder for
it. `check` and `build` test templates against your checkout, not against
what is published.

`ci` has to find the language in a checkout. It does when `layers` reads the
language's files. If it has no reader, or shares its files with another
language, name the files that give it away in `marks`, and the languages it
replaces in `insteadOf`. [`deno.nix`](./lib/languages/deno.nix) shows both.
Then add a sample to `lib/ci/tests/test_detect.py`.

[direnv-ext]: https://marketplace.visualstudio.com/items?itemName=mkhl.direnv
