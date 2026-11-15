# A language for the tests of ci: it has a test tool, and the checkout never
# has what that tool waits for.
_: {
  tests = {
    run = [
      ''
        when never.words true
      ''
    ];
  };
}
