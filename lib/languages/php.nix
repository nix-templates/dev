# PHP.
{ pkgs, ... }:
{
  description = "PHP development environment: Phpactor, PHPStan, Psalm, PHP_CodeSniffer and php-cs-fixer";

  tools = with pkgs; [
    # Toolchain
    php
    phpPackages.composer

    # Language server
    phpactor

    # Static analysis and coding-standard linters
    phpstan
    phpPackages.psalm
    phpPackages.php-codesniffer

    # Formatter
    phpPackages.php-cs-fixer

    # Tests
    phpunit
  ];

  semgrep = true;
  trivy = true;

  lint = ''
    when phpstan.neon phpstan analyse --no-progress
    when psalm.xml psalm --no-progress
    when phpcs.xml phpcs
  '';

  fmt = ''
    when_any '*.php' php-cs-fixer fix .
  '';

  scan = ''
    when composer.lock composer audit
  '';

  arch = [
    ''
      if [ -e deptrac.yaml ] && [ -x vendor/bin/deptrac ]; then
        run vendor/bin/deptrac analyse
      fi
    ''
  ];

  tests = {
    run = [
      ''
        when_any 'phpunit*.xml*' phpunit
      ''
    ];
    mutation = [
      ''
        if found 'infection.json*' && [ -x vendor/bin/infection ]; then
          run vendor/bin/infection
        fi
      ''
    ];
  };
}
