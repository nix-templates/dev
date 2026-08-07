# Nix flake templates for batteries-included dev environments

Every template in this repository gives you a `nix develop` shell that already
contains the language server, linters, formatters and security scanners that
language's community actually uses, wired into direnv, VS Code and Neovim so
they work the moment you open the project.

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

## Templates

Templates marked (new) are ones this repository adds on top of the upstream
[the-nix-way/dev-templates][upstream] set.

### Systems and application languages

| Template | Tooling |
| :--- | :--- |
| [`c-cpp`](./c-cpp/) | `cmake`, `ninja`, `meson`, `bear`, `gtest`, `lcov`, `doxygen`, `clang-tools`, ... |
| [`crystal`](./crystal/) (new) | `crystal`, `shards`, `crystalline`, `ameba`, `semgrep`, `trivy` |
| [`csharp`](./csharp/) | `dotnet-sdk_10`, `msbuild`, `mono`, `omnisharp-roslyn`, `csharpier`, `netcoredbg`, `semgrep`, `trivy` |
| [`dart`](./dart/) (new) | `dart`, `flutter`, `semgrep`, `trivy` |
| [`fortran`](./fortran/) (new) | `gfortran`, `fpm`, `fortls`, `fprettify`, `semgrep`, `trivy` |
| [`fsharp`](./fsharp/) (new) | `dotnet-sdk_10`, `msbuild`, `fsautocomplete`, `fantomas`, `semgrep`, `trivy` |
| [`go`](./go/) | `go`, `gotools`, `gotestsum`, `delve`, `gopls`, `golangci-lint`, `go-tools`, `gofumpt`, ... |
| [`haxe`](./haxe/) | `haxe`, `neko`, `semgrep`, `trivy` |
| [`java`](./java/) | `jdk`, `maven`, `gradle`, `jdt-language-server`, `checkstyle`, `pmd`, `google-java-format`, `semgrep`, ... |
| [`julia`](./julia/) (new) | `julia`, `pandoc`, `trivy` |
| [`kotlin`](./kotlin/) | `kotlin`, `gradle`, `jdk`, `kotlin-language-server`, `ktlint`, `detekt`, `ktfmt`, `semgrep`, ... |
| [`nim`](./nim/) | `nim`, `nimble`, `nimlangserver`, `nph`, `semgrep`, `trivy` |
| [`odin`](./odin/) | `odin`, `ols`, `trivy` |
| [`perl`](./perl/) (new) | `perl`, `perlnavigator`, `PLS`, `PerlCritic`, `PerlTidy`, `semgrep`, `trivy` |
| [`php`](./php/) | `php`, `composer`, `phpactor`, `phpstan`, `psalm`, `php-codesniffer`, `php-cs-fixer`, `semgrep`, ... |
| [`python`](./python/) | `python`, `uv`, `basedpyright`, `ruff`, `mypy`, `vulture`, `bandit`, `semgrep`, ... |
| [`racket`](./racket/) (new) | `racket`, `trivy` |
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
| [`erlang`](./erlang/) (new) | `erlang`, `rebar3`, `erlang-language-platform`, `erlfmt`, `semgrep`, `trivy` |
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
| [`graphql`](./graphql/) (new) | `nodejs`, `pnpm`, `typescript`, `graphql-language-service-cli`, `typescript-language-server`, `eslint`, `biome`, `prettier`, ... |
| [`node`](./node/) | `nodejs`, `pnpm`, `yarn`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `eslint`, `oxlint`, ... |
| [`typescript`](./typescript/) (new) | `nodejs`, `pnpm`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `biome`, `eslint`, `oxlint`, ... |
| [`web`](./web/) (new) | `nodejs`, `pnpm`, `typescript`, `typescript-language-server`, `vscode-langservers-extracted`, `tailwindcss-language-server`, `emmet-language-server`, `eslint`, ... |

### Scripting and glue

| Template | Tooling |
| :--- | :--- |
| [`assembly`](./assembly/) (new) | `nasm`, `yasm`, `binutils`, `asm-lsp`, `radare2`, `lldb` |
| [`groovy`](./groovy/) (new) | `groovy`, `gradle`, `jdk`, `groovy-language-server`, `npm-groovy-lint`, `semgrep`, `trivy` |
| [`lua`](./lua/) (new) | `lua5_4`, `luajit`, `lua-language-server`, `selene`, `luacheck`, `stylua`, `semgrep`, `trivy` |
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
| [`ansible`](./ansible/) (new) | `ansible`, `sshpass`, `ansible-language-server`, `yaml-language-server`, `ansible-lint`, `yamllint`, `yamlfmt`, `trivy` |
| [`docker`](./docker/) (new) | `docker-compose`, `docker-buildx`, `podman`, `buildah`, `skopeo`, `dive`, `dockerfile-language-server-nodejs`, `yaml-language-server`, ... |
| [`github-actions`](./github-actions/) (new) | `act`, `gh`, `yaml-language-server`, `actionlint`, `yamllint`, `yamlfmt`, `zizmor`, `trivy` |
| [`hashi`](./hashi/) | `terraform`, `vault`, `nomad`, `consul`, `packer`, `terragrunt`, `nomad-autoscaler`, `nomad-pack`, ... |
| [`kubernetes`](./kubernetes/) (new) | `kubectl`, `kubernetes-helm`, `kustomize`, `kubectx`, `k9s`, `stern`, `yaml-language-server`, `helm-ls`, ... |
| [`pulumi`](./pulumi/) | `pulumi-bin`, `python313`, `go`, `nodejs`, `jdk`, `maven`, `gopls`, `basedpyright`, ... |
| [`terraform`](./terraform/) (new) | `opentofu`, `terragrunt`, `terraform-ls`, `tflint`, `terraform-docs`, `tfsec`, `checkov`, `trivy` |

### Data, hardware and documents

| Template | Tooling |
| :--- | :--- |
| [`hdl`](./hdl/) (new) | `verilator`, `iverilog`, `ghdl`, `yosys`, `gtkwave`, `verible`, `svls` |
| [`jupyter`](./jupyter/) | `python`, `ipykernel`, `poetry`, `uv`, `basedpyright`, `ruff`, `mypy`, `nbstripout`, ... |
| [`latex`](./latex/) | `scheme-full`, `tectonic`, `texlab`, `vale`, `pandoc` |
| [`markdown`](./markdown/) (new) | `marksman`, `harper`, `markdownlint-cli2`, `vale`, `lychee`, `mdformat`, `prettier`, `pandoc`, ... |
| [`platformio`](./platformio/) | `platformio`, `cmake`, `ninja`, `bear`, `clang-tools`, `cppcheck`, `codespell`, `gtest`, ... |
| [`presenterm`](./presenterm/) | `presenterm`, `mermaid-cli`, `typst`, `pandoc`, `marksman`, `harper`, `markdownlint-cli2`, `vale`, ... |
| [`r`](./r/) | `rEnv`, `pandoc`, `scheme-full`, `trivy` |
| [`solidity`](./solidity/) (new) | `solc`, `solc-select`, `foundry`, `nodejs`, `pnpm`, `slither-analyzer`, `semgrep`, `trivy` |
| [`sql`](./sql/) (new) | `postgresql`, `sqlite`, `pgcli`, `usql`, `sqls`, `sqlfluff`, `sqruff`, `pgformatter`, ... |
| [`typst`](./typst/) | `typst`, `tinymist`, `typstyle`, `vale`, `pandoc` |

### Starting point

| Template | Tooling |
| :--- | :--- |
| [`empty`](./empty/) | `treefmt`, `dprint`, `taplo`, `yamlfmt`, `yamllint`, `markdownlint-cli2`, `actionlint`, `semgrep`, ... |

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
```

[upstream]: https://github.com/the-nix-way/dev-templates
[direnv-ext]: https://marketplace.visualstudio.com/items?itemName=mkhl.direnv
[direnv-vim]: https://github.com/direnv/direnv.vim
