# A language for the tests of ci: every command has something of it to run.
# Its files end in .words.
_: {
  quality = ''
    for_each '*.words' test -s
  '';

  style = ''
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
