"""The one exception type ytchat shows to the user."""

from typing import Literal

from .safe_text import printable

# What kind of problem it is. The CLI uses this to title the error and to decide
# what to do, e.g. an API key the vendor rejects ("auth") is never saved.
ErrorKind = Literal["auth", "model", "config", "network", "limit", "input", "other"]


class AppError(Exception):
    """A problem the user can fix: `problem` says what went wrong, `fix` what to do.

    Both are often built from outside text (vendor and yt-dlp messages, links), so they are
    cleaned of terminal control characters here, once, for every place they're printed.
    """

    def __init__(self, problem: str, fix: str | None = None, kind: ErrorKind = "other") -> None:
        problem = printable(problem)
        super().__init__(problem)
        self.problem = problem
        self.fix = printable(fix) if fix else fix
        self.kind = kind
