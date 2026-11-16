{
  pkgs,
  lib,
  dev,
  profiles,
}:
lib.concatMap (
  profile:
  let
    baseMetadata = dev.frameworks.${profile.name};
    metadata = baseMetadata // (baseMetadata.variants.${profile.version} or { });
    key = metadata.bundleKey or "${metadata.bundle}-${profile.version}";
    module = metadata.module {
      inherit pkgs lib;
      options.frameworkVersion = profile.version;
    };
    command =
      name: text:
      pkgs.writeShellApplication {
        inherit name text;
        runtimeInputs = module.tools;
        excludeShellChecks = [ "SC2329" ];
      };
    quality = command "node-quality" (
      (builtins.readFile ../../helpers.sh) + module.preflight + module.quality + ''exit "$status"''
    );
    style = command "node-style" (
      (builtins.readFile ../../helpers.sh) + module.preflight + module.style + ''exit "$status"''
    );
    fixture =
      if lib.hasPrefix "vue" key then
        {
          file = "ExampleApp.vue";
          good = "<template><main>Hello</main></template>";
          bad = ''<template><main id="a" id="b">Broken</main></template>'';
        }
      else if lib.hasPrefix "svelte" key then
        {
          file = "ExampleApp.svelte";
          good = "<main>Hello</main>";
          bad = ''<main id="a" id="b">Broken</main>'';
        }
      else if key == "astro" then
        {
          file = "ExampleApp.astro";
          good = "<main>Hello</main>";
          bad = ''<main set:html="a" set:text="b" />'';
        }
      else if key == "typescript" then
        {
          file = "index.ts";
          good = "export const answer: number = 42;";
          bad = "debugger; export const answer = 42;";
        }
      else
        {
          file = "pages/index.jsx";
          good = "export default function App() { return <main>Hello</main>; }";
          bad = ''import { useState } from "react"; export default function App() { if (window.flag) { useState(0); } return <main>Hello</main>; }'';
        };
    compiler = metadata.compiler or "";
    compilerArg =
      {
        angular = "build --configuration development --progress=false";
        nuxt = "typecheck";
        svelte = "--fail-on-warnings";
        sveltekit = "sync";
        astro = "";
        nest = "build";
        docusaurus = "build";
        vitepress = "build";
        typescript = "--noEmit";
      }
      .${compiler} or "";
  in
  [
    (pkgs.runCommand "${profile.name}-${profile.version}-tools" { } ''
      export HOME="$TMPDIR"
      export DVT_NODE_LOG="$PWD/dispatch.log"
      mkdir -p node_modules/${metadata.package} node_modules/.bin pages
      echo '{"version":"${profile.version}.0.0"}' > node_modules/${metadata.package}/package.json
      ${lib.concatMapStrings (requirement: ''
        mkdir -p node_modules/${requirement.package}
        echo '{"version":"${
          if requirement.version == "$framework" then profile.version else requirement.version
        }.0.0"}' > node_modules/${requirement.package}/package.json
      '') (metadata.requires or [ ])}
      echo '{"private":true}' > package.json
      echo '{"lockfileVersion":3}' > package-lock.json
      echo '${fixture.good}' > ${fixture.file}
      # Framework compilers are project tools. Test dispatch independently of the
      # real, locked ESLint and Prettier bundles used above them.
      cat > node_modules/.bin/project-tool <<'JS'
      #!${pkgs.nodejs}/bin/node
      require('fs').appendFileSync(process.env.DVT_NODE_LOG, process.argv.slice(2).join(' ') + '\n');
      if (process.env.CI !== 'true') process.exit(9);
      process.exit(Number(process.env.DVT_NODE_FAIL || 0));
      JS
      chmod +x node_modules/.bin/project-tool
      for tool in ng vue-tsc nuxt svelte-check svelte-kit astro-check nest docusaurus vitepress tsc; do
        ln -s project-tool node_modules/.bin/$tool
      done
      ${lib.optionalString (compiler == "typescript") "echo '{}' > tsconfig.json"}
      echo 'throw new Error("local tool leaked");' > eslint.config.js
      ${style}/bin/node-style > style.log 2>&1 || { cat style.log; exit 1; }
      ${quality}/bin/node-quality > quality.log 2>&1 || { cat quality.log; exit 1; }
      ${lib.optionalString (compiler != "") ''
        test -f dispatch.log
        grep -F -- '${compilerArg}' dispatch.log
        export DVT_NODE_FAIL=23
        if ${quality}/bin/node-quality > failed-compiler.log 2>&1; then
          echo 'project compiler failure was ignored'; exit 1
        fi
        unset DVT_NODE_FAIL
      ''}
      echo '${fixture.bad}' > ${fixture.file}
      if ${quality}/bin/node-quality > failed.log 2>&1; then
        echo 'framework quality failed to catch invalid source'; exit 1
      fi
      ${lib.optionalString (compiler != "") ''
        echo '${fixture.good}' > ${fixture.file}
        rm node_modules/.bin/*
        if ${quality}/bin/node-quality > missing.log 2>&1; then
          echo 'missing project compiler was ignored'; exit 1
        fi
        grep 'missing; no dependency was added' missing.log
      ''}
      echo '{"version":"99.0.0"}' > node_modules/${metadata.package}/package.json
      if ${quality}/bin/node-quality > mismatch.log 2>&1; then
        echo 'mismatched framework version passed'; exit 1
      fi
      grep 'does not match' mismatch.log
      # Formatting may change whitespace, but neither dependency manifest is resolved.
      ${pkgs.python3}/bin/python3 -c 'import json; assert json.load(open("package.json")) == {"private": True}; assert json.load(open("package-lock.json")) == {"lockfileVersion": 3}'
      touch $out
    '')
  ]
) (lib.filter (profile: (dev.frameworks.${profile.name}.adapter or "") == "node") profiles)
