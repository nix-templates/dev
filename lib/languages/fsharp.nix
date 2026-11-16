# F#.
{ pkgs, ... }:
{
  description = "F# development environment: FsAutoComplete and Fantomas";

  tools = with pkgs; [
    # Toolchain
    dotnet-sdk_10
    msbuild

    # Language server
    fsautocomplete

    # Formatter
    fantomas

  ];

  semgrep = true;
  trivy = true;

  # The shell needs a C compiler and its wrapper.
  needsCC = true;

  env = {
    DOTNET_CLI_TELEMETRY_OPTOUT = "1";
    DOTNET_NOLOGO = "1";
  };

  quality = ''
    when_any '*.fsproj' dotnet build --no-restore --warnaserror
  '';

  style = ''
    when_any '*.fs' fantomas .
  '';

  security = ''
    when_any '*.fsproj' dotnet list package --vulnerable --include-transitive
  '';

  tests = {
    run = [
      ''
        when_any '*.fsproj' dotnet test --no-restore
      ''
    ];
    coverage = [
      ''
        when_any '*.fsproj' dotnet test --no-restore --collect:"XPlat Code Coverage"
      ''
    ];
    mutation = [
      ''
        when stryker-config.json dotnet stryker
      ''
    ];
  };
}
