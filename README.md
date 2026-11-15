# Nix flake templates for batteries-included dev environments

Every template in this repository gives you a `nix develop` shell that already
contains the language server, linters, formatters and security scanners that
language's community actually uses, wired into direnv, VS Code and Neovim so
they work the moment you open the project.

There are two ways to use it:

- **Copy a template.** `nix flake init` writes one language's environment into
  your project. It is yours from then on; see [Getting started](#getting-started).
- **Take it as a library.** Your flake names this repository as an input and
  lists its languages. One shell covers all of them, `nix flake update` brings
  in every later improvement, and `archcheck` enforces your architecture rules.
  See [Use it as a library](#use-it-as-a-library).

## What you get

Each template ships six files:

| File | What it does |
| :--- | :----------- |
| `flake.nix` | The devShell: toolchain, LSP, linters, formatters, SAST and secret scanners |
| `.envrc` | `use flake`, so direnv puts all of it on `PATH` on `cd` |
| `.vscode/extensions.json` | Recommends `mkhl.direnv` plus the language's extensions |
| `.vscode/settings.json` | Points every extension at the devShell's binaries and turns on format-on-save |
| `.vscode/tasks.json` | `lint`, `fmt` and `scan` as VS Code tasks |
| `.nvim.lua` | Plugin-free LSP setup via `vim.lsp.config`, format-on-save and `:DevLint` / `:DevFmt` / `:DevScan` |

Every devShell also exposes three commands, so the terminal, VS Code and Neovim
all run the same checks:

```shell
lint    # every linter and static analyser for this language
fmt     # every formatter, in place
scan    # SAST, dependency and secret scanning
```

## Getting started

Initialise a template (`${ENV}` is any name from the tables below):

```shell
nix flake init -t github:nix-templates/dev#${ENV}
```

or start a new project directory:

```shell
nix flake new -t github:nix-templates/dev#${ENV} ${NEW_PROJECT_DIRECTORY}
```

Then turn the environment on:

```shell
direnv allow      # with direnv installed; recommended
nix develop       # without it
```

### Editor setup, once per machine

**VS Code.** Install the [direnv extension][direnv-ext]. It loads the devShell
into the editor process so extensions find the binaries. Opening the project
prompts you to install the rest of the recommended extensions.

```shell
code --install-extension mkhl.direnv
```

**Neovim.** The `.nvim.lua` files are project-local configuration, which Neovim
only reads when `exrc` is on. Add this to your `init.lua`:

```lua
vim.o.exrc = true
```

The first time you open a project Neovim asks you to trust the file; answer with
`:trust`. Nothing else is needed, since the LSP setup uses Neovim 0.11+'s
built-in `vim.lsp.config` and `vim.lsp.enable` with no plugins at all. Pair it
with [direnv.vim][direnv-vim] if you want the environment loaded when you `:cd`
around.

**Anything else.** Launch it from a directory where direnv is active and it
inherits the whole toolchain through `PATH`.

## Use it as a library

A template is a copy, so what improves here later does not reach a project that
already has one. A project that should keep up names this repository as a flake
input and says which languages it is written in:

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
        languages = [ "rust" "python" "nix" "shell" ];
        src = self;
      };
    in
    {
      devShells.x86_64-linux.default = project.devShell;
      checks.x86_64-linux = project.checks;
    };
}
```

`nix flake update dev` then brings in newer tools and rules. The
[`project`](./project/) template is this flake for every supported system, with
a starting `architecture.toml`:

```shell
nix flake init -t github:nix-templates/dev#project
```

The shell has the tools of every language you listed, and four commands:

```shell
lint          # every linter of every listed language, then archcheck
fmt           # every formatter, in place
fmt --check   # the same formatters, reporting only: for CI
scan          # SAST, dependency and secret scanning
archcheck     # the rules in architecture.toml
```

The tools come from the `pkgs` you pass in, so they match the versions your
project builds with. That matters most for Rust: clippy's lints change with
every release, so pass your pinned toolchain as `rustToolchain`.

| `mkProject` argument | What it is |
| :--- | :--- |
| `pkgs` | Your package set. Required. |
| `languages` | Names from the table below, in the order their checks should run. A module of your own works too: `{ pkgs, lib, options }: { tools; lint; fmt; fmtCheck; scan; }`, every part optional. |
| `src` | Your source tree, `self` in a flake. Turns on `checks`. |
| `rustToolchain` | One derivation with `cargo`, `rustc`, `clippy` and `rustfmt`. Default: the four from `pkgs`. |
| `python` | The Python interpreter. Default: `pkgs.python3`. |
| `extraTools` | More packages for the shell and the commands' `PATH`. |

| It returns | What it is |
| :--- | :--- |
| `devShell` | A shell with all tools and commands. |
| `packages`, `tools`, `env` | The same pieces, for a shell you build yourself: `pkgs.mkShell { inherit (project) packages env; }`. |
| `commands` | `lint`, `fmt`, `scan` and `archcheck` as packages, for CI jobs and `nix run`. |
| `checks` | `archcheck` as a flake check. It runs inside the Nix sandbox, so `nix flake check` covers it and unchanged sources are not checked twice. It fails without an `architecture.toml`, so leave `src` out until you have one. `lint` and `scan` need the network and stay commands. |

| Language | Tooling |
| :--- | :--- |
| `c-cpp` | `clang-tools`, `cppcheck`, `include-what-you-use`, `codespell`, `flawfinder`, `cmake`, `ninja`, `meson`, ... |
| `nix` | `nixd`, `statix`, `deadnix`, `nixfmt`, `vulnix`, ... |
| `python` | `uv`, `basedpyright`, `ruff`, `mypy`, `vulture`, `bandit` |
| `qml` | `qmllint`, `qmlformat`, `qmlls` |
| `rust` | your toolchain, `rust-analyzer`, `cargo-nextest`, `cargo-deny`, `cargo-machete`, `cargo-audit`, `taplo`, ... |
| `shell` | `bash`, `bats`, `bash-language-server`, `shellcheck`, `shfmt` |

Every project also gets `typos`, `editorconfig-checker`, `gitleaks` and `trivy`,
and `semgrep` when one of its languages has rules for it.

The library knows these six languages so far. The other templates still carry
their own copy of their tools and scripts.

## Architecture rules with archcheck

`archcheck` reads `architecture.toml` at the root of a repository and fails
when code breaks the rules in it. Two kinds of rule:

- **Dependency rules.** The code is divided into layers. A file may use its own
  layer and the layers its layer names, and nothing else.
- **Purity rules.** A layer marked `pure` is a functional core: the same input
  gives the same output, and nothing outside the function changes. It may not
  touch files, the network, processes, the clock, the environment, randomness,
  threads or shared mutable state. That work belongs in the layers around it.

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
forbid_external = ["tokio"]   # this layer may not depend on these packages
hint = "Adapters talk to one outside system each."

[[layer]]
name = "app"
paths = ["src"]
may_use = ["core", "adapters"]
```

The first layer whose `paths` match a file is that file's layer, so the narrow
ones go first. `*` stays inside one path segment and `**` crosses them.

A failure names the file and line, the rule, and what to do instead:

```text
core/plan.py:2: layer: 'core' may not use 'adapters': adapters.disk is adapters/disk.py
    fix: 'core' may use no other layer. Move what both need into a layer 'core' may use,
    or define the interface in 'core' and implement it in 'adapters'. Do not add this to
    the baseline.
```

| Other settings | What it does |
| :--- | :--- |
| `strict = true` | A source file in no layer is a failure, so new code must be given a place. |
| `exclude = ["generated"]` | Paths to leave out. Hidden directories and build output are left out already. |
| `include_tests = true` | Check test code too. By default tests may use anything. |
| `[purity] allow = ["logging"]` | Let pure layers use this after all. |
| `[purity] forbid = ["numpy"]` | Keep this out of pure layers as well. |
| `[python] roots = ["python"]` | Directories that hold top-level packages, when they are not found by themselves. |
| `[cpp] include_dirs = ["include"]` | Where quoted includes are looked up, besides next to the file. |
| `[javascript.aliases] "@/" = "src/"` | Import prefixes that stand for a directory. |

### Adopting it in existing code

Existing code rarely follows new rules at once. The baseline holds the
violations that were there on the day the rules arrived:

```shell
archcheck --explain   # which files are in which layer
archcheck --accept    # write today's violations to architecture-baseline.json
```

From then on a violation in the baseline passes and a new one fails. The
baseline may only get shorter: an entry that no longer occurs fails too, until
`archcheck --prune` takes it out, so the change that fixes a violation also
shortens the list. In CI, `archcheck --since origin/main` also fails when the
baseline has entries that `origin/main`'s baseline lacks.

### How it reads each language

| Language | What it reads | What it does not see |
| :--- | :--- | :--- |
| Rust | Crate dependencies from every `Cargo.toml`, exactly. Inside a crate, `use` declarations and qualified paths, with modules found by the standard file layout. | `#[path]` modules, names brought in by glob imports or macros. |
| Python | Imports from the syntax tree, relative ones included, plus calls such as `open()`, `print()` and `datetime.now()`, and `global`. | Imports made at run time with `importlib`. |
| JavaScript, TypeScript | `import`, `export ... from`, `require()` and `import()`, plus uses of `fetch`, `Date.now()`, `Math.random()`, `console`, the DOM and timers. | Paths mapped in `tsconfig.json`; map them under `[javascript.aliases]`. |
| C, C++ | `#include` lines. | Anything behind the preprocessor. |

It reads the text, not the compiler's view, so treat it as the rule that keeps
the structure in place, next to the language's own tools: `clippy.toml` with
`disallowed-methods`, `cargo-deny`, `import-linter`, `eslint-plugin-functional`.
A file it cannot parse fails the check instead of passing unread.

## Templates

### Systems and application languages

| Template | Tooling |
| :--- | :--- |
| [`c-cpp`](./c-cpp/) | `cmake`, `ninja`, `meson`, `bear`, `gtest`, `lcov`, `doxygen`, `clang-tools`, ... |
| [`crystal`](./crystal/) | `crystal`, `shards`, `crystalline`, `ameba`, `semgrep`, `trivy` |
| [`csharp`](./csharp/) | `dotnet-sdk_10`, `msbuild`, `mono`, `omnisharp-roslyn`, `csharpier`, `netcoredbg`, `semgrep`, `trivy` |
| [`dart`](./dart/) | `dart`, `flutter`, `semgrep`, `trivy` |
| [`fortran`](./fortran/) | `gfortran`, `fpm`, `fortls`, `fprettify`, `semgrep`, `trivy` |
| [`fsharp`](./fsharp/) | `dotnet-sdk_10`, `msbuild`, `fsautocomplete`, `fantomas`, `semgrep`, `trivy` |
| [`go`](./go/) | `go`, `gotools`, `gotestsum`, `delve`, `gopls`, `golangci-lint`, `go-tools`, `gofumpt`, ... |
| [`haxe`](./haxe/) | `haxe`, `neko`, `semgrep`, `trivy` |
| [`java`](./java/) | `jdk`, `maven`, `gradle`, `jdt-language-server`, `checkstyle`, `pmd`, `google-java-format`, `semgrep`, ... |
| [`julia`](./julia/) | `julia`, `pandoc`, `trivy` |
| [`kotlin`](./kotlin/) | `kotlin`, `gradle`, `jdk`, `kotlin-language-server`, `ktlint`, `detekt`, `ktfmt`, `semgrep`, ... |
| [`nim`](./nim/) | `nim`, `nimble`, `nimlangserver`, `nph`, `semgrep`, `trivy` |
| [`odin`](./odin/) | `odin`, `ols`, `trivy` |
| [`perl`](./perl/) | `perl`, `perlnavigator`, `PLS`, `PerlCritic`, `PerlTidy`, `semgrep`, `trivy` |
| [`php`](./php/) | `php`, `composer`, `phpactor`, `phpstan`, `psalm`, `php-codesniffer`, `php-cs-fixer`, `semgrep`, ... |
| [`python`](./python/) | `python`, `uv`, `basedpyright`, `ruff`, `mypy`, `vulture`, `bandit`, `semgrep`, ... |
| [`racket`](./racket/) | `racket`, `trivy` |
| [`ruby`](./ruby/) | `ruby_3_4`, `ruby-lsp`, `solargraph`, `rubocop`, `bundler-audit`, `semgrep`, `trivy` |
| [`rust`](./rust/) | `rustToolchain`, `cargo-edit`, `cargo-watch`, `cargo-nextest`, `bacon`, `rust-analyzer`, `cargo-deny`, `cargo-machete`, ... |
| [`scala`](./scala/) | `scala`, `sbt`, `scala-cli`, `mill`, `coursier`, `jdk`, `metals`, `scalafix`, ... |
| [`swift`](./swift/) | `swift`, `sourcekit-lsp`, `swiftlint`, `swiftformat`, `semgrep`, `trivy` |
| [`vlang`](./vlang/) | `vlang`, `trivy` |
| [`zig`](./zig/) | `zig`, `zls`, `lldb`, `trivy` |

### Functional languages

| Template | Tooling |
| :--- | :--- |
| [`clojure`](./clojure/) | `clojure`, `leiningen`, `boot`, `babashka`, `clojure-lsp`, `clj-kondo`, `cljfmt`, `zprint`, ... |
| [`elixir`](./elixir/) | `elixir`, `elixir-ls`, `nodejs`, `semgrep`, `trivy` |
| [`elm`](./elm/) | `elm`, `elm-json`, `elm2nix`, `elm-language-server`, `elm-review`, `elm-test`, `elm-format`, `nodejs`, ... |
| [`erlang`](./erlang/) | `erlang`, `rebar3`, `erlang-language-platform`, `erlfmt`, `semgrep`, `trivy` |
| [`gleam`](./gleam/) | `gleam`, `erlang`, `rebar3`, `nodejs`, `semgrep`, `trivy` |
| [`haskell`](./haskell/) | `ghc`, `cabal-install`, `stack`, `hoogle`, `haskell-language-server`, `hlint`, `ormolu`, `cabal-fmt`, ... |
| [`lean4`](./lean4/) | `lean4`, `trivy` |
| [`ocaml`](./ocaml/) | `ocaml`, `opam`, `dune_3`, `utop`, `odoc`, `ocaml-lsp`, `ocamlformat`, `semgrep`, ... |
| [`purescript`](./purescript/) | `purescript`, `spago`, `nodejs`, `esbuild`, `semgrep`, `trivy` |

### JavaScript and the web

| Template | Tooling |
| :--- | :--- |
| [`bun`](./bun/) | `bun`, `nodejs`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `biome`, `oxlint`, `prettier`, ... |
| [`deno`](./deno/) | `deno`, `semgrep`, `trivy` |
| [`graphql`](./graphql/) | `nodejs`, `pnpm`, `typescript`, `graphql-language-service-cli`, `typescript-language-server`, `eslint`, `biome`, `prettier`, ... |
| [`node`](./node/) | `nodejs`, `pnpm`, `yarn`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `eslint`, `oxlint`, ... |
| [`typescript`](./typescript/) | `nodejs`, `pnpm`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `biome`, `eslint`, `oxlint`, ... |
| [`web`](./web/) | `nodejs`, `pnpm`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `tailwindcss-language-server`, `emmet-language-server`, `eslint`, ... |

### Scripting and glue

| Template | Tooling |
| :--- | :--- |
| [`assembly`](./assembly/) | `nasm`, `yasm`, `binutils`, `asm-lsp`, `radare2`, `lldb` |
| [`groovy`](./groovy/) | `groovy`, `gradle`, `jdk`, `groovy-language-server`, `npm-groovy-lint`, `semgrep`, `trivy` |
| [`lua`](./lua/) | `lua5_4`, `luajit`, `lua-language-server`, `selene`, `luacheck`, `stylua`, `semgrep`, `trivy` |
| [`powershell`](./powershell/) | `powershell`, `powershell-editor-services`, `semgrep`, `trivy` |
| [`shell`](./shell/) | `bash`, `bats`, `bash-language-server`, `shellcheck`, `shfmt`, `semgrep`, `trivy` |
| [`swi-prolog`](./swi-prolog/) | `swi-prolog` |

### Configuration and policy languages

| Template | Tooling |
| :--- | :--- |
| [`cue`](./cue/) | `cue`, `cuelsp`, `trivy` |
| [`dhall`](./dhall/) | `dhall`, `dhall-json`, `dhall-bash`, `dhall-docs`, `dhall-nix`, `dhall-lsp-server`, `trivy` |
| [`nickel`](./nickel/) | `nickel`, `nls`, `trivy` |
| [`nix`](./nix/) | `nixd`, `statix`, `deadnix`, `nixfmt`, `vulnix`, `nix-tree`, `nix-diff`, `nurl`, ... |
| [`opa`](./opa/) | `open-policy-agent`, `conftest`, `regal`, `trivy` |
| [`protobuf`](./protobuf/) | `protobuf`, `buf`, `grpcurl`, `protolint`, `trivy` |

### Infrastructure and operations

| Template | Tooling |
| :--- | :--- |
| [`ansible`](./ansible/) | `ansible`, `sshpass`, `ansible-language-server`, `yaml-language-server`, `ansible-lint`, `yamllint`, `yamlfmt`, `trivy` |
| [`docker`](./docker/) | `docker-compose`, `docker-buildx`, `podman`, `buildah`, `skopeo`, `dive`, `dockerfile-language-server-nodejs`, `yaml-language-server`, ... |
| [`github-actions`](./github-actions/) | `act`, `gh`, `yaml-language-server`, `actionlint`, `yamllint`, `yamlfmt`, `zizmor`, `trivy` |
| [`hashi`](./hashi/) | `terraform`, `vault`, `nomad`, `consul`, `packer`, `terragrunt`, `nomad-autoscaler`, `nomad-pack`, ... |
| [`kubernetes`](./kubernetes/) | `kubectl`, `kubernetes-helm`, `kustomize`, `kubectx`, `k9s`, `stern`, `yaml-language-server`, `helm-ls`, ... |
| [`pulumi`](./pulumi/) | `pulumi-bin`, `python313`, `go`, `nodejs`, `jdk`, `maven`, `gopls`, `basedpyright`, ... |
| [`terraform`](./terraform/) | `opentofu`, `terragrunt`, `terraform-ls`, `tflint`, `terraform-docs`, `tfsec`, `checkov`, `trivy` |

### Data, hardware and documents

| Template | Tooling |
| :--- | :--- |
| [`hdl`](./hdl/) | `verilator`, `iverilog`, `ghdl`, `yosys`, `gtkwave`, `verible`, `svls` |
| [`jupyter`](./jupyter/) | `python`, `ipykernel`, `poetry`, `uv`, `basedpyright`, `ruff`, `mypy`, `nbstripout`, ... |
| [`latex`](./latex/) | `scheme-full`, `tectonic`, `texlab`, `vale`, `pandoc` |
| [`markdown`](./markdown/) | `marksman`, `harper`, `markdownlint-cli2`, `vale`, `lychee`, `mdformat`, `prettier`, `pandoc`, ... |
| [`platformio`](./platformio/) | `platformio`, `cmake`, `ninja`, `bear`, `clang-tools`, `cppcheck`, `codespell`, `gtest`, ... |
| [`presenterm`](./presenterm/) | `presenterm`, `mermaid-cli`, `typst`, `pandoc`, `marksman`, `harper`, `markdownlint-cli2`, `vale`, ... |
| [`r`](./r/) | `rEnv`, `pandoc`, `scheme-full`, `trivy` |
| [`solidity`](./solidity/) | `solc`, `solc-select`, `foundry`, `nodejs`, `pnpm`, `slither-analyzer`, `semgrep`, `trivy` |
| [`sql`](./sql/) | `postgresql`, `sqlite`, `pgcli`, `usql`, `sqls`, `sqlfluff`, `sqruff`, `pgformatter`, ... |
| [`typst`](./typst/) | `typst`, `tinymist`, `typstyle`, `vale`, `pandoc` |

### Starting point

| Template | Tooling |
| :--- | :--- |
| [`empty`](./empty/) | `treefmt`, `dprint`, `taplo`, `yamlfmt`, `yamllint`, `markdownlint-cli2`, `actionlint`, `semgrep`, ... |
| [`project`](./project/) | The library, for a project in several languages: you list them in `flake.nix`. Comes with `architecture.toml` and no editor files. |

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
check                 # nix flake check, every template
build                 # build every template's devShell
format                # nixfmt every .nix file
nix flake check       # the library: archcheck's tests, and shellcheck on its scripts
```

The library is in [`lib/`](./lib/):

| Path | What it is |
| :--- | :--- |
| `lib/default.nix` | `mkProject`, and the list of languages |
| `lib/languages/` | One file per language: its tools and its part of `lint`, `fmt` and `scan` |
| `lib/helpers.sh` | The shell helpers those parts use (`run`, `run_on`, `when`, ...) |
| `lib/archcheck/` | `archcheck`, in Python with no dependencies, and its tests |

To add a language to the library, add its file under `lib/languages/` and its
name in `lib/default.nix`. `nix flake check` then checks its scripts together
with all the others.

A template that takes this repository as an input, as `project` does, is checked
by `check` and `build` against your checkout, not against what is published.

[direnv-ext]: https://marketplace.visualstudio.com/items?itemName=mkhl.direnv
[direnv-vim]: https://github.com/direnv/direnv.vim
