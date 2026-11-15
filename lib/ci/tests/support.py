"""What the tests of ci share: small checkouts, a stand-in for nix, and dev shells with commands in them."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, "..", ".."))
BASH = shutil.which("bash")

with open(os.path.join(LIB, "helpers.sh"), encoding="utf-8") as _handle:
    HELPERS = _handle.read()

# The marks of every language as `lib.marks` gives them, when the flake's check passes them in.
REAL_MARKS = None
if os.environ.get("DEV_CI_MARKS"):
    with open(os.environ["DEV_CI_MARKS"], encoding="utf-8") as _handle:
        REAL_MARKS = json.load(_handle)

# Enough of them for the tests that are about something else.
MARKS = REAL_MARKS or {
    "deno": {"marks": ["deno.json", "deno.jsonc"], "insteadOf": ["node", "typescript"]},
    "github-actions": {"marks": [".github/workflows/*.yml", ".github/workflows/*.yaml"], "insteadOf": []},
    "hashi": {"marks": [], "insteadOf": []},
    "markdown": {"marks": ["*.md"], "insteadOf": []},
    "nix": {"marks": None, "insteadOf": []},
    "node": {"marks": None, "insteadOf": []},
    "python": {"marks": None, "insteadOf": []},
    "shell": {"marks": None, "insteadOf": []},
    "terraform": {"marks": None, "insteadOf": []},
    "typescript": {"marks": ["tsconfig.json"], "insteadOf": ["node"]},
}


def git(root: str, *arguments: str) -> str:
    identity = ["-c", "user.name=test", "-c", "user.email=test@example.org", "-c", "commit.gpgsign=false"]
    return subprocess.run(["git", "-C", root, *identity, *arguments], check=True, capture_output=True, text=True).stdout.strip()


def checkout(files: dict[str, str], commit: bool = True) -> str:
    """A git checkout with these files, all of them added, and committed unless told otherwise."""
    root = tempfile.mkdtemp(prefix="ci-test-")
    for path, text in files.items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(text).lstrip("\n"))
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    if commit:
        git(root, "commit", "-q", "--allow-empty", "-m", "start")
    return root


def shell(commands: dict[str, str], hook: str = "", own: tuple[str, ...] = ()) -> str:
    """The script of a dev shell with these commands on PATH.

    A command is its body after the library's helpers, as mkProject writes
    it. The ones named in own are a project's own programs: the body alone.
    """
    directory = tempfile.mkdtemp(prefix="ci-shell-")
    for name, body in commands.items():
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"#!{BASH}\n" + ("" if name in own else HELPERS) + textwrap.dedent(body))
        os.chmod(path, 0o755)
    return f'export PATH="{directory}${{PATH:+:$PATH}}"\n{hook}\n'


class Nix:
    """A stand-in for nix on PATH. It answers from files and notes every call."""

    SCRIPT = """\
        #!/bin/sh
        here=$(dirname "$0")
        printf '%s\\n' "$*" >> "$here/calls"
        answer() {
          if [ -e "$here/$1" ]; then
            cat "$here/$1"
          else
            echo "error: nix has no answer for $1" >&2
            exit 1
          fi
        }
        case " $* " in
          *" eval "*) answer eval ;;
          *" print-dev-env --file "*) answer composed ;;
          *" print-dev-env "*) answer own ;;
          *) echo "error: unexpected: $*" >&2; exit 64 ;;
        esac
        """

    def __init__(self):
        self.directory = tempfile.mkdtemp(prefix="ci-nix-")
        path = os.path.join(self.directory, "nix")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(self.SCRIPT))
        os.chmod(path, 0o755)

    def answer(self, question: str, text: str | None) -> None:
        """What nix prints for `eval`, for the checkout's `own` dev shell or for a `composed` one. None: it fails."""
        path = os.path.join(self.directory, question)
        if text is None:
            if os.path.exists(path):
                os.unlink(path)
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    @property
    def calls(self) -> list[str]:
        try:
            with open(os.path.join(self.directory, "calls"), encoding="utf-8") as handle:
                return handle.read().splitlines()
        except FileNotFoundError:
            return []

    def asked(self, word: str) -> int:
        return sum(1 for call in self.calls if f" {word} " in f" {call} ")


@dataclass
class Result:
    code: int
    out: str
    err: str

    @property
    def said(self) -> list[str]:
        """The lines of ci's own."""
        return [line for line in self.err.splitlines() if line.startswith("ci: ")]


def ci(root: str, *arguments: str, nix: Nix | None = None, cache: str | None = None, path: str | None = None) -> Result:
    """Run ci in a checkout, with the stand-in for nix in front of PATH."""
    settings = {
        "toolbox": "/toolbox",
        "nixpkgs": "/nixpkgs",
        "system": "x86_64-linux",
        "revision": "0123456789abcdef0123456789abcdef01234567",
        "nixpkgsRevision": "fedcba9876543210fedcba9876543210fedcba98",
        "bash": BASH,
        "env": shutil.which("env"),
        "marks": MARKS,
    }
    scratch = tempfile.mkdtemp(prefix="ci-settings-")
    with open(os.path.join(scratch, "settings.json"), "w", encoding="utf-8") as handle:
        json.dump(settings, handle)
    environment = dict(os.environ)
    environment["DEV_CI_SETTINGS"] = os.path.join(scratch, "settings.json")
    environment["PYTHONPATH"] = os.pathsep.join([os.path.join(LIB, "ci"), os.path.join(LIB, "layers"), os.path.join(LIB, "..", "mcp")])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["XDG_CACHE_HOME"] = cache or tempfile.mkdtemp(prefix="ci-cache-")
    if path is not None:
        environment["PATH"] = path
    elif nix:
        environment["PATH"] = nix.directory + os.pathsep + environment["PATH"]
    done = subprocess.run([sys.executable, "-m", "ci", *arguments], cwd=root, env=environment, capture_output=True, text=True, check=False)
    return Result(done.returncode, done.stdout, done.stderr)
