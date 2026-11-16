# Ruby.
{ pkgs, ... }:
{
  description = "Ruby development environment: ruby-lsp, RuboCop and bundler-audit";

  tools = with pkgs; [
    # Toolchain
    ruby_3_4

    # Language servers
    ruby-lsp
    solargraph

    # Linter and formatter in one
    rubocop

    # Security: dependency advisories plus generic scanning
    bundler-audit

  ];

  semgrep = true;
  trivy = true;

  quality = ''
    when_any '*.rb' rubocop --fail-level warning
  '';

  style = ''
    when_any '*.rb' rubocop --autocorrect-all --fail-level fatal
  '';

  security = ''
    when Gemfile.lock bundle-audit check --update
  '';

  architecture = [
    ''
      when packwerk.yml bundle exec packwerk check
    ''
  ];

  tests = {
    run = [
      ''
        when .rspec bundle exec rspec
      ''
      ''
        if [ -e Rakefile ] && [ -d test ]; then
          run bundle exec rake test
        fi
      ''
    ];
  };
}
