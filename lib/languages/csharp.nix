# C#.
{ pkgs, ... }:
{
  description = "C# development environment: OmniSharp, CSharpier and the .NET SDK analysers";

  tools = with pkgs; [
    # Toolchain
    dotnet-sdk_10
    msbuild
    mono

    # Language server
    omnisharp-roslyn

    # Formatter (dotnet format ships with the SDK)
    csharpier

    # Debugger
    netcoredbg

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
    when_any '*.csproj' dotnet build --no-restore --warnaserror
  '';

  style = ''
    when_any '*.cs' csharpier format .
  '';

  security = ''
    when_any '*.csproj' dotnet list package --vulnerable --include-transitive
  '';

  tests = {
    run = [
      ''
        when_any '*.csproj' dotnet test --no-restore
      ''
    ];
    coverage = [
      ''
        when_any '*.csproj' dotnet test --no-restore --collect:"XPlat Code Coverage"
      ''
    ];
    mutation = [
      ''
        when stryker-config.json dotnet stryker
      ''
    ];
  };
}
