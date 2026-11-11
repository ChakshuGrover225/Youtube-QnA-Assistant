"""The one exception type ytchat shows to the user."""

from typing import Literal

# What kind of problem it is. The CLI uses this to title the error and to decide
# what to do, e.g. an API key the vendor rejects ("auth") is never saved.
ErrorKind = Literal["auth", "model", "config", "network", "limit", "input", "other"]


class AppError(Exception):
    """A problem the user can fix: `problem` says what went wrong, `fix` what to do."""

    def __init__(self, problem: str, fix: str | None = None, kind: ErrorKind = "other") -> None:
        super().__init__(problem)
        self.problem = problem
        self.fix = fix
        self.kind = kind
