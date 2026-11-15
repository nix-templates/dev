"""The environment a command runs in: a dev shell, taken apart.

Nix can print a dev shell as a bash script that sets it up. That script is
the whole environment, so this module asks for it, keeps it, and runs it to
get the variables a command needs. Two dev shells are known: the default one
of the checkout's own flake, and the one lib/ci/compose.nix makes for a list
of languages.

Asking Nix costs seconds and a pipeline asks five times, so the script is
kept under the user's cache directory, by what it was made from. A kept
script is used as long as every store path on its PATH still exists.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass

NIX = ("nix", "--extra-experimental-features", "nix-command flakes")
KEEP_DAYS = 14

# The fmt every dev shell has is the one of coreutils, which formats no code.
NOT_A_COMMAND = ("coreutils", "busybox", "uutils", "toybox")


class CannotRun(Exception):
    """No environment could be made, or the one made cannot be entered."""


def stands_in(found: str) -> bool:
    """Whether a program on a dev shell's PATH is one that every dev shell has, and not one the project brought."""
    parts = found.split("/")
    return found.startswith("/nix/store/") and len(parts) > 3 and parts[3].partition("-")[2].startswith(NOT_A_COMMAND)


def _cache() -> str | None:
    base = os.environ.get("XDG_CACHE_HOME")
    if not base and os.environ.get("HOME"):
        base = os.path.join(os.environ["HOME"], ".cache")
    return os.path.join(base, "nix-templates-dev", "ci") if base else None


def _key(*made_from: str) -> str:
    return hashlib.sha256("\0".join(made_from).encode()).hexdigest()[:32]


def kept(key: str) -> str | None:
    """The script kept under key, or None."""
    cache = _cache()
    if not cache:
        return None
    path = os.path.join(cache, key + ".sh")
    try:
        with open(path, encoding="utf-8") as handle:
            script = handle.read()
        os.utime(path)
    except OSError:
        return None
    return script or None


def keep(key: str, script: str) -> None:
    """Keep a script under key, and drop the ones nothing has asked for in two weeks."""
    cache = _cache()
    if not cache:
        return
    try:
        os.makedirs(cache, exist_ok=True)
        old = time.time() - KEEP_DAYS * 86400
        for name in os.listdir(cache):
            path = os.path.join(cache, name)
            if os.path.getmtime(path) < old:
                os.unlink(path)
        handle, scratch = tempfile.mkstemp(dir=cache, prefix=".new-")
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(script)
        os.replace(scratch, os.path.join(cache, key + ".sh"))
    except OSError:
        return


def forget(key: str) -> None:
    cache = _cache()
    if cache:
        try:
            os.unlink(os.path.join(cache, key + ".sh"))
        except OSError:
            pass


def _nix(arguments: list[str], what: str) -> str:
    """Run nix and give what it printed. Its own messages go to the log as they come."""
    try:
        result = subprocess.run([*NIX, *arguments], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, check=False)
    except FileNotFoundError:
        raise CannotRun("there is no nix on PATH") from None
    if result.returncode != 0:
        raise CannotRun(f"{what} (nix ended with status {result.returncode}; what it said is above)")
    return result.stdout.decode("utf-8", "replace")


def _nix_string(text: str) -> str:
    return json.dumps(text).replace("${", "\\${")


def _git(root: str, *arguments: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", root, *arguments], capture_output=True, check=False)
    except OSError:
        return None
    return result.stdout.decode("utf-8", "replace").strip() if result.returncode == 0 else None


def own_key(root: str, system: str) -> str | None:
    """What a checkout's own dev shell is kept under: its commit, when nothing differs from that commit.

    A flake without a lock file may give another shell tomorrow, so its shell is never kept.
    """
    if not os.path.isfile(os.path.join(root, "flake.lock")):
        return None
    commit = _git(root, "rev-parse", "--verify", "HEAD")
    changed = _git(root, "status", "--porcelain", "--untracked-files=no")
    if not commit or changed is None or changed:
        return None
    return _key("own", commit, _git(root, "rev-parse", "--show-prefix") or "", system)


def own(root: str, system: str, key: str | None) -> str | None:
    """The default dev shell of the flake at root as a script, or None when the flake has no such shell.

    CannotRun when the flake does not evaluate or the shell does not build: a
    checkout that brings its own environment gets no other one behind its back.
    """
    script = kept(key) if key else None
    if script:
        return script
    has = _nix(
        [
            "eval",
            "--impure",
            "--json",
            "--expr",
            f"let flake = builtins.getFlake {_nix_string(root)}; in ((flake.devShells or {{ }}).{_nix_string(system)} or {{ }}) ? default",
        ],
        "this checkout's flake.nix could not be read",
    )
    if json.loads(has) is not True:
        return None
    script = _nix(
        ["print-dev-env", "--no-write-lock-file", f"{root}#devShells.{system}.default"],
        "the dev shell of this checkout's flake could not be made",
    )
    if key:
        keep(key, script)
    return script


def composed_key(languages: list[str], settings: dict) -> str:
    return _key("composed", settings["toolbox"], settings["nixpkgs"], settings["system"], *languages)


def composed(languages: list[str], settings: dict, key: str) -> str:
    """The dev shell lib/ci/compose.nix makes for these languages, as a script."""
    script = kept(key)
    if script:
        return script
    script = _nix(
        [
            "print-dev-env",
            "--file",
            os.path.join(settings["toolbox"], "lib", "ci", "compose.nix"),
            "--argstr",
            "nixpkgs",
            settings["nixpkgs"],
            "--argstr",
            "system",
            settings["system"],
            "--arg",
            "languages",
            "[ " + " ".join(_nix_string(language) for language in languages) + " ]",
        ],
        "no environment could be made for these languages",
    )
    keep(key, script)
    return script


@dataclass
class Entered:
    """A dev shell that was set up."""

    # What a program started in it gets as its environment.
    variables: dict[str, str]
    # The directories the shell itself put on PATH, without what was there before.
    path: list[str]
    # What setting it up printed.
    said: str

    def intact(self) -> bool:
        """Whether every store path the shell put on PATH is still there."""
        return all(os.path.isdir(directory) for directory in self.path if directory.startswith("/nix/store/"))

    def command(self, name: str) -> str | None:
        """Where the shell has a command of this name, or None when it brings none."""
        found = shutil.which(name, path=os.pathsep.join(self.path))
        return None if not found or stands_in(found) else found

    def leave(self) -> None:
        """Remove the directory the script made for temporary files."""
        scratch = self.variables.get("NIX_BUILD_TOP", "")
        if os.path.basename(scratch).startswith("nix-shell."):
            shutil.rmtree(scratch, ignore_errors=True)


def enter(script: str, settings: dict) -> Entered:
    """Run a dev shell's script and take the environment it leaves behind."""
    before = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="ci-") as scratch:
        at = {name: os.path.join(scratch, name) for name in ("script", "said", "variables")}
        with open(at["script"], "w", encoding="utf-8") as out:
            out.write(script)
        # The script ends with the shell's own hook, whose status says nothing.
        subprocess.run(
            [settings["bash"], "-c", 'source "$1" > "$2" 2>&1; exec "$3" -0 > "$4"', "ci", at["script"], at["said"], settings["env"], at["variables"]],
            stdin=subprocess.DEVNULL,
            check=False,
        )
        said = ""
        if os.path.exists(at["said"]):
            with open(at["said"], encoding="utf-8", errors="replace") as handle:
                said = handle.read()
        dumped = b""
        if os.path.exists(at["variables"]):
            with open(at["variables"], "rb") as handle:
                dumped = handle.read()
    variables = {}
    for item in dumped.split(b"\0"):
        name, equals, value = item.partition(b"=")
        if equals and name != b"_":
            variables[os.fsdecode(name)] = os.fsdecode(value)
    if "PATH" not in variables:
        raise CannotRun("the dev shell could not be entered" + (", it said:\n" + said.rstrip() if said.strip() else ""))
    path = variables["PATH"]
    # The script puts the PATH from before behind the shell's own.
    if before and path.endswith(os.pathsep + before):
        path = path[: -len(before) - 1]
    return Entered(variables, [directory for directory in path.split(os.pathsep) if directory], said)


def pinned(root: str) -> str | None:
    """The revision of nix-templates/dev that the checkout's flake.lock names, if it names one."""
    try:
        with open(os.path.join(root, "flake.lock"), encoding="utf-8") as handle:
            nodes = json.load(handle).get("nodes", {})
    except (OSError, ValueError):
        return None
    for node in nodes.values():
        locked = node.get("locked", {}) if isinstance(node, dict) else {}
        if (locked.get("owner", "").lower(), locked.get("repo", "").lower()) == ("nix-templates", "dev"):
            return locked.get("rev")
    return None
