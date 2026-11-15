"""The few records every part of arch passes around."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ref:
    """One reference from a source file to something else.

    kind is "internal" (target is a repository-relative file), "external"
    (target is a package name and path is what was written, such as
    "std::fs::read") or "effect" (target names a side effect that is not an
    import, such as "println!" or "global").
    """

    file: str
    line: int
    kind: str
    target: str
    path: str = ""


@dataclass(frozen=True)
class Violation:
    rule: str  # "layer", "purity", "external", "unassigned" or "unreadable"
    file: str
    line: int
    target: str
    message: str
    fix: str
    count: int = 1

    @property
    def key(self) -> tuple[str, str, str]:
        # No line number: moving code inside a file must not change the key.
        return (self.rule, self.file, self.target)


@dataclass
class Scan:
    """What the extractors found."""

    files: list[str] = field(default_factory=list)  # source files that rules apply to
    refs: list[Ref] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unreadable: list[tuple[str, str]] = field(default_factory=list)  # files that could not be parsed, with why
