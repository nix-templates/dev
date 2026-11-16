# PowerShell.
{ pkgs, ... }:
{
  description = "PowerShell development environment with PowerShell Editor Services";

  tools = with pkgs; [
    # Toolchain
    powershell

    # Language server (also provides PSScriptAnalyzer diagnostics)
    powershell-editor-services

  ];

  semgrep = true;
  trivy = true;

  style = ''
    run typos --write-changes .
  '';

  tests = {
    run = [
      ''
        # Pester is not in nixpkgs: Install-Module -Name Pester -Scope CurrentUser
        when_any '*.Tests.ps1' pwsh -NoProfile -Command 'Invoke-Pester -CI'
      ''
    ];
  };
}
