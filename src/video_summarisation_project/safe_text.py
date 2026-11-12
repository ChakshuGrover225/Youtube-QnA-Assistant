"""Removing terminal control characters from text that came from outside ytchat.

Model replies, vendor error messages and transcripts can contain characters a terminal
obeys instead of showing: ESC sequences that clear the screen, rewrite what's shown, set
the window title or write to the clipboard (OSC 52), and their one-byte C1 forms. rich
strips only a few (bell, backspace, carriage return), not ESC, so everything from an
outside source passes through `printable()` before it is printed or saved to a file.
"""

import re

_UNSAFE = re.compile(
    "["
    "\x00-\x08\x0b-\x1f\x7f"  # C0 controls and DEL, including ESC (\x1b); keeps \t and \n
    "\x80-\x9f"  # C1 controls: \x9b works like "ESC [" in some terminals
    "‪-‮⁦-⁩"  # bidi overrides and isolates, which can make text display in a misleading order
    "]"
)


def printable(text: str) -> str:
    """`text` without control characters (tabs and newlines are kept)."""
    return _UNSAFE.sub("", text)
