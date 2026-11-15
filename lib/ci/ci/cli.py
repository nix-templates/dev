"""The ci command: one of the five commands on a checkout, the way a CI job needs it.

A checkout that has a flake whose default dev shell brings the command runs
it there, so the project's own pin decides the tools. Any other checkout gets
a dev shell made for the languages found in it, from the revision of this
repository that ci itself came from.

The commands are style, security, quality, architecture and tests. Four of
them had other names before: fmt, scan, lint and layers. ci does not take
those. A checkout that pins a revision from before only has them under the old
names, though, and its pin is what decides its tools, so there ci runs the
command the checkout has.

It exits 0 when the check passed, 1 when it found something and 2 when it
could not run. Every line of its own starts with "ci: " and goes to stderr;
the first names the environment. A run that passed without having checked
anything says so on a line that starts with "ci: checked nothing".
"""

import json
import os
import signal
import subprocess
import sys

from . import __version__, environment, watch
from .environment import CannotRun

COMMANDS = ("style", "security", "quality", "architecture", "tests")
# What four of them were called before. A project that pins a revision from
# before still has them under these names in its dev shell.
FORMERLY = {"style": "fmt", "security": "scan", "quality": "lint", "architecture": "layers"}
RULES = "architecture.toml"

USAGE = f"""\
usage: ci [--strict[=CASE,...]] <{"|".join(COMMANDS)}> [arguments]
       ci --languages

Runs one of the five commands on the checkout in the current directory.
A checkout with a flake whose default dev shell has the command runs it
there. Any other checkout gets a dev shell made for the languages found in it.

  style         is `style --check` here: nothing is rewritten
  architecture  fails when the checkout has no {RULES}
  arguments     go to the command as they are, as in `ci architecture --since origin/main`

It exits 0 when the check passed, 1 when it found something, 2 when it could
not run. A run that passed without checking anything prints a line that
starts with "ci: checked nothing (CASE)". --strict makes those runs fail,
all of them or the cases named: {", ".join(watch.CASES)}.

  --languages  print the languages found in the checkout, and stop
"""


def languages_of(root: str, settings: dict) -> dict[str, list[str]]:
    # Finding languages loads every reader of `architecture`. A checkout with its own dev shell never needs them.
    from . import detect

    return detect.found(root, settings["marks"])


def say(text: str) -> None:
    print(f"ci: {text}", file=sys.stderr, flush=True)


def short(revision: str) -> str:
    """A commit as twelve characters, with what follows it kept; anything else as it is."""
    commit, dash, rest = revision.partition("-")
    if len(commit) == 40 and all(c in "0123456789abcdef" for c in commit):
        return commit[:12] + dash + rest
    return revision


def option(arguments: list[str], name: str) -> str | None:
    """The value of `--name VALUE` or `--name=VALUE` among a command's arguments; the last one counts."""
    value = None
    for index, argument in enumerate(arguments):
        if argument == name and index + 1 < len(arguments):
            value = arguments[index + 1]
        elif argument.startswith(name + "="):
            value = argument[len(name) + 1 :]
    return value


def rules(arguments: list[str]) -> tuple[str | None, tuple[str, str] | None]:
    """What `architecture` with these arguments would have nothing to check with.

    First the architecture.toml that is missing, when the command would skip
    because of it. Then the reason a comparison with --since compares nothing.
    """
    if any(argument in ("--languages", "--version", "--help", "-h") for argument in arguments):
        return None, None
    at = option(arguments, "--root") or "."
    given = option(arguments, "--config")
    config = given or os.path.normpath(os.path.join(at, RULES))
    if not given and not os.path.exists(config):
        return config, None
    since = option(arguments, "--since")
    if since:

        def git(*query: str) -> bool:
            try:
                return subprocess.run(["git", "-C", at, *query], capture_output=True, check=False).returncode == 0
            except OSError:
                return False

        inside = os.path.relpath(config, at)
        if git("rev-parse", "--verify", "--quiet", f"{since}^{{commit}}") and not git("cat-file", "-e", f"{since}:./{inside}"):
            return None, ("no-comparison", f"{since} has no {inside}, so --since compared nothing")
    return None, None


def made_here(program: str) -> bool:
    """Whether a program is one of the library's commands: a script with the library's `run` in it."""
    try:
        with open(program, "rb") as handle:
            return watch.MADE_HERE.encode() in handle.read(1 << 20)
    except OSError:
        return False


def enter(script: str, again, key: str | None, settings: dict) -> environment.Entered:
    """Set up the dev shell of a script.

    A kept script may name store paths that were collected since. Then it is
    dropped and Nix is asked again, with again(), which brings them back.
    """
    entered = environment.enter(script, settings)
    if entered.intact():
        return entered
    entered.leave()
    if key:
        environment.forget(key)
    entered = environment.enter(again(), settings)
    if not entered.intact():
        entered.leave()
        raise CannotRun("the dev shell names store paths that are not there")
    return entered


def follow(program: str, arguments: list[str], root: str, entered: environment.Entered) -> tuple[int, watch.Seen]:
    """Run the command, pass on what it prints, and keep count of what it ran."""
    seen = watch.Seen()
    process = subprocess.Popen([program, *arguments], cwd=root, env=entered.variables, stdout=subprocess.PIPE)

    def pass_on(number, _frame):
        process.send_signal(number)

    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, pass_on)
    out = sys.stdout.buffer
    for line in process.stdout:
        out.write(line)
        out.flush()
        seen.line(line.decode("utf-8", "replace").rstrip("\n"))
    return process.wait(), seen


def check(command: str, arguments: list[str], root: str, settings: dict, strict: set[str]) -> int:
    cases: list[tuple[str, str]] = []
    if command == "architecture":
        missing, uncompared = rules(arguments)
        if missing:
            say(
                f"architecture: there is no {missing} in this checkout, so nothing was checked. Add one that names the layers "
                'and what each may use. A project with nothing to keep apart says so with one layer: paths = ["."].'
            )
            return 1
        if uncompared:
            cases.append(uncompared)
    if command == "style" and "--check" not in arguments:
        arguments = ["--check", *arguments]

    system = settings["system"]
    entered = program = why = None
    if os.path.isfile(os.path.join(root, "flake.nix")):
        key = environment.own_key(root, system)
        script = environment.own(root, system, key)
        if script is None:
            why = "this checkout's flake has no default dev shell"
        else:
            entered = enter(script, lambda: environment.own(root, system, key), key, settings)
            # A project that pins a revision from before the commands were renamed has the old one.
            before = FORMERLY.get(command)
            program = entered.command(command) or (entered.command(before) if before else None)
            if program is None:
                entered.leave()
                entered = None
                why = f"the dev shell of this checkout's flake has no {command}"

    if entered is not None:
        ours = made_here(program)
        if not ours:
            origin = f"its own {command}, not the one of nix-templates/dev"
        elif environment.pinned(root):
            origin = f"nix-templates/dev {short(environment.pinned(root))}"
        else:
            origin = "nix-templates/dev, at a revision its flake.lock does not name"
        if os.path.basename(program) != command:
            origin += f", where it is still called {os.path.basename(program)}"
        say(f"{command} in this checkout's own dev shell ({origin})")
    else:
        languages = languages_of(root, settings)
        names = ", ".join(languages) or "no language"
        say(
            f"{command} in a dev shell made for {names} by nix-templates/dev {short(settings['revision'])} "
            f"with nixpkgs {short(settings['nixpkgsRevision'])}"
        )
        if why:
            say(f"{why}, so one was made here")
        if languages:
            say("languages found: " + ", ".join(f"{name} ({len(files)} file{'s' if len(files) != 1 else ''})" for name, files in languages.items()))
        else:
            cases.append(("no-languages", "no language of nix-templates/dev was found in this checkout, so only what every project gets ran"))
        key = environment.composed_key(list(languages), settings)

        def compose() -> str:
            return environment.composed(list(languages), settings, key)

        entered = enter(compose(), compose, key, settings)
        program = entered.command(command)
        if program is None:
            entered.leave()
            raise CannotRun(f"the dev shell made here has no {command}")
        ours = True

    if entered.said.strip():
        sys.stderr.write(entered.said if entered.said.endswith("\n") else entered.said + "\n")
        sys.stderr.flush()
    try:
        status, seen = follow(program, arguments, root, entered)
    finally:
        entered.leave()

    cases.extend(watch.unchecked(command, seen, ours))
    for name, text in cases:
        say(f"checked nothing ({name}): {text}")
    code = watch.verdict(status)
    if status not in (0, 1, 2):
        say(f"{command} ended with status {status}, which counts as {'could not run' if code == 2 else 'found something'}")
    failing = sorted({name for name, _ in cases} & strict)
    if code == 0 and failing:
        say(f"failing: --strict was given for {', '.join(failing)}")
        code = 1
    return code


def main(argv: list[str] | None = None, settings: dict | str | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not isinstance(settings, dict):
        with open(settings or os.environ["DEV_CI_SETTINGS"], encoding="utf-8") as handle:
            settings = json.load(handle)

    strict: set[str] = set()
    while argv and argv[0].startswith("-"):
        given = argv.pop(0)
        if given in ("-h", "--help"):
            print(USAGE, end="")
            return 0
        if given == "--version":
            print(f"ci {__version__} of nix-templates/dev {settings['revision']}")
            return 0
        if given == "--languages":
            for name, files in languages_of(os.getcwd(), settings).items():
                print(f"{name}: {len(files)} file{'s' if len(files) != 1 else ''}, such as {files[0]}")
            return 0
        if given == "--strict":
            strict = set(watch.CASES)
        elif given.startswith("--strict="):
            names = [name for name in given.partition("=")[2].split(",") if name]
            unknown = [name for name in names if name not in watch.CASES]
            if unknown or not names:
                say(f"--strict takes these cases: {', '.join(watch.CASES)}" + (f" (not {', '.join(unknown)})" if unknown else ""))
                return 2
            strict |= set(names)
        else:
            say(f"there is no option {given}")
            sys.stderr.write(USAGE)
            return 2
    if not argv or argv[0] not in COMMANDS:
        now = {before: command for command, before in FORMERLY.items()}
        if argv and argv[0] in now:
            say(f"there is no command {argv[0]}. It is called {now[argv[0]]} now")
        else:
            say(f"there is no command {argv[0]}" if argv else "which command?")
        sys.stderr.write(USAGE)
        return 2

    command, arguments = argv[0], argv[1:]
    try:
        return check(command, arguments, os.getcwd(), settings, strict)
    except CannotRun as reason:
        say(f"{command} could not run: {reason}")
        return 2
