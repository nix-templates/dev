# A language for the tests of ci: every command has something of it to run.
# Its files end in .words.
_: {
  lint = ''
    for_each '*.words' test -s
  '';

  fmt = ''
    for_each '*.words' sed -i 's/[[:space:]]*$//'
  '';

  tests = {
    run = [
      ''
        run env
      ''
    ];
  };
}
