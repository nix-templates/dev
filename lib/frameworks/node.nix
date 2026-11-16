# The linter host, parser, plugins and formatter are one locked tool environment.
# Neither node_modules nor the application's package manifest is changed.
baseMetadata:
{
  pkgs,
  lib,
  options,
  ...
}:
let
  readerPython = pkgs.python3.withPackages (ps: [ ps.pyyaml ]);
  version = options.frameworkVersion or baseMetadata.defaultVersion;
  metadata = baseMetadata // (baseMetadata.variants.${version} or { });
  key = metadata.bundleKey or "${metadata.bundle}-${version}";
  compiler = metadata.compiler or (if metadata.bundle == "vue" then "vue" else "typescript");
  hashes = builtins.fromJSON (builtins.readFile ./bundles/hashes.json);
  bundle = pkgs.buildNpmPackage {
    pname = "dvt-${key}";
    version = "1";
    src = ./bundles + "/${key}";
    npmDepsHash = hashes.${key};
    npmFlags = [ "--ignore-scripts" ];
    dontNpmBuild = true;
    installPhase = ''
      runHook preInstall
      mkdir -p $out/lib/dvt
      cp -r node_modules eslint.config.mjs $out/lib/dvt/
      runHook postInstall
    '';
  };
  config = "${bundle}/lib/dvt/eslint.config.mjs";
  quality = pkgs.writeShellApplication {
    name = "dvt-${metadata.bundle}-quality";
    runtimeInputs = [ pkgs.nodejs ];
    text = ''
      unset NODE_PATH NODE_OPTIONS
      export ESLINT_USE_FLAT_CONFIG=true
      exec node ${bundle}/lib/dvt/node_modules/eslint/bin/eslint.js --no-config-lookup --max-warnings 0 --config ${config} "$@"
    '';
  };
  style = pkgs.writeShellApplication {
    name = "dvt-${metadata.bundle}-style";
    runtimeInputs = [ pkgs.nodejs ];
    text = ''
      unset NODE_PATH NODE_OPTIONS
      exec node ${bundle}/lib/dvt/node_modules/prettier/bin/prettier.cjs ${lib.optionalString (lib.hasPrefix "svelte" key) "--plugin ${bundle}/lib/dvt/node_modules/prettier-plugin-svelte/plugin.js"} ${
        lib.optionalString (
          key == "astro"
        ) "--plugin ${bundle}/lib/dvt/node_modules/prettier-plugin-astro/dist/index.js"
      } "$@"
    '';
  };
  compilerChecks = {
    typescript = ''
      if [ -f tsconfig.json ]; then run js_exec tsc --noEmit; fi
    '';
    vue = ''
      if [ -f tsconfig.json ]; then run js_exec vue-tsc --noEmit; fi
    '';
    angular = "run js_exec ng build --configuration development --progress=false";
    nuxt = ''
      js_require vue-tsc
      run js_exec nuxt typecheck
    '';
    svelte = "run js_exec svelte-check --fail-on-warnings";
    sveltekit = ''
      run js_exec svelte-kit sync
      run js_exec svelte-check --fail-on-warnings
    '';
    astro = "run js_exec astro-check";
    nest = "run js_exec nest build";
    docusaurus = "run js_exec docusaurus build";
    vitepress = "run js_exec vitepress build";
  };
  guard = ''
    ${readerPython}/bin/python3 -I -B ${./version_guard.py} npm ${lib.escapeShellArg metadata.package} ${lib.escapeShellArg version}
  ''
  + lib.concatMapStrings (requirement: ''
    ${readerPython}/bin/python3 -I -B ${./version_guard.py} ${lib.escapeShellArg requirement.kind} ${lib.escapeShellArg requirement.package} ${
      lib.escapeShellArg (if requirement.version == "$framework" then version else requirement.version)
    }
  '') (metadata.requires or [ ]);
in
{
  defaults.node = pkgs.nodejs_22;
  tools = [
    quality
    style
  ];
  replace = lib.genAttrs metadata.languages (
    _:
    [
      "quality"
      "style"
    ]
    ++ lib.optional (compiler == "angular") "tests"
  );
  # Every command verifies the installed framework release line before checking.
  preflight = guard + (import ../project-node.nix { inherit pkgs; }) + "export CI=true\n";
  quality = ''
    run ${quality}/bin/dvt-${metadata.bundle}-quality .
  ''
  + compilerChecks.${compiler}
  + "\n";
  tests = lib.optionalAttrs (compiler == "angular") {
    run = [ "run js_exec ng test --watch=false" ];
  };
  style = ''
    run ${style}/bin/dvt-${metadata.bundle}-style --write --ignore-unknown .
  '';
}
