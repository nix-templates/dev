"""What a command's output tells about what it checked.

The five commands print `:: tool arguments` for every tool they run and
`:: skipping tool (why)` for every one they leave out. Counting those lines
is how a run that passed is told from a run that had nothing to check. The
commands of every revision print them, so this works for a project that pins
an older one.
"""

import re
from dataclasses import dataclass, field

# The line `run` in lib/helpers.sh prints, and with it the proof that a
# program on PATH is one of the library's commands.
MADE_HERE = 'echo ":: $*"'

# A line that starts with ":: " and is not a tool: a skip, the header of
# `tests` or of `architecture` (`layers` before), or a command's own count.
TOOL = re.compile(r"^:: (?!skipping |tests: |(?:architecture|layers)(?: |$)|checked nothing: )")
FOR_LANGUAGE = re.compile(r"^:: checked nothing: (?P<command>.+) for (?P<language>.+)$")
NO_TOOL = re.compile(r"^:: checked nothing: .+ ran no tool$")
SUMMARY = re.compile(r"^(?:architecture|layers): (?:ok|FAIL: .*) \((?P<read>\d+) files checked, (?P<placed>\d+) of them in a layer")

# The ways a command passes without having checked anything, by the name
# --strict takes for each.
CASES = ("no-languages", "no-tool", "language", "no-layer-files", "no-comparison", "own-command")


@dataclass
class Seen:
    """What the lines of one command's output added up to."""

    tools: int = 0
    # The command said itself that it ran no tool. It knows better than a count of
    # its lines: a tool that found nothing to check has a line and did not run.
    none: bool = False
    languages: list[str] = field(default_factory=list)
    # What `architecture` read, and how much of it is in a layer.
    read: int | None = None
    placed: int | None = None

    def line(self, text: str) -> None:
        if TOOL.match(text):
            self.tools += 1
            return
        if NO_TOOL.match(text):
            self.none = True
            return
        nothing = FOR_LANGUAGE.match(text)
        if nothing:
            self.languages.append(nothing["language"])
            return
        summary = SUMMARY.match(text)
        if summary:
            self.read, self.placed = int(summary["read"]), int(summary["placed"])


def unchecked(command: str, seen: Seen, made_here: bool) -> list[tuple[str, str]]:
    """The cases this run fell into, each with the line that says so."""
    if not made_here:
        return [("own-command", f"{command} is this project's own program, so what it checked is not known")]
    cases = []
    if command == "architecture":
        # A checkout with nothing for `architecture` to read has said so by having an architecture.toml.
        if seen.read and seen.placed == 0:
            cases.append(("no-layer-files", f"architecture read {seen.read} files and architecture.toml puts none of them in a layer"))
        return cases
    if seen.tools == 0 or seen.none:
        cases.append(("no-tool", f"{command} ran no tool"))
    cases.extend(("language", f"{command} ran nothing for {language}") for language in seen.languages)
    return cases


def verdict(status: int) -> int:
    """0 passed, 1 found something, 2 could not run.

    The commands keep to that themselves. What is left is a command that died:
    killed by a signal, or a status the shell gives when a program is missing
    or may not be run.
    """
    if status in (0, 1, 2):
        return status
    return 2 if status < 0 or status >= 126 else 1
