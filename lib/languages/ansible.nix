# Ansible.
{ pkgs, ... }:
{
  description = "Ansible environment: ansible-language-server, ansible-lint and yamllint";

  # Playbooks are YAML like any other, so it takes Ansible's own config to tell.
  marks = [
    "ansible.cfg"
    ".ansible-lint"
  ];

  tools = with pkgs; [
    # Toolchain
    ansible
    sshpass

    # Language servers
    ansible-language-server
    yaml-language-server

    # Linters
    ansible-lint
    yamllint

    # Formatter
    yamlfmt

    # Security
    trivy

    # Tests: run roles against throwaway instances
    molecule
  ];

  lint = ''
    run yamllint --strict .
    when_any '*.yml' ansible-lint --offline
  '';

  fmt = ''
    run yamlfmt .
  '';

  scan = ''
    run trivy config --exit-code 1 --skip-dirs .direnv .
  '';

  tests = {
    run = [
      ''
        when molecule molecule test
      ''
    ];
  };
}
