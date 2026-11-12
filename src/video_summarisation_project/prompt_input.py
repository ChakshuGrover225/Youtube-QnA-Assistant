"""The main prompt in a real terminal: slash commands are suggested as you type.

Typing "/" lists every command, "/s" only those starting with /s, and so on. Tab or the
arrow keys pick one. Up/down also recall earlier lines.

This needs keystroke-level input, which plain input() (and so rich's console.input) can't
do, so it uses prompt_toolkit. It's only used when stdin and stdout are a terminal: piped
input, Git Bash's mintty (not a Windows console) and the tests keep plain line input.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console

# command name -> (usage, description), as in cli.COMMANDS
Commands = Mapping[str, tuple[str, str]]
LineReader = Callable[[str], str]  # rich-markup prompt -> the line typed


class SlashCommandCompleter(Completer):
    """Suggests the commands that start with what has been typed so far."""

    def __init__(self, commands: Commands) -> None:
        self.commands = commands

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        typed = document.text_before_cursor.lstrip()
        if not typed.startswith("/") or " " in typed:  # not a command, or already typing its argument
            return
        for name, (usage, description) in self.commands.items():
            if name.startswith(typed.lower()):
                yield Completion(name, start_position=-len(typed), display=usage, display_meta=description)


def make_session(commands: Commands, **kwargs: Any) -> PromptSession:
    return PromptSession(completer=SlashCommandCompleter(commands), complete_while_typing=True, **kwargs)


def terminal_reader(console: Console, commands: Commands) -> LineReader | None:
    """A line reader with command suggestions, or None when ytchat isn't in an interactive terminal."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return None
    try:
        session = make_session(commands)
    except Exception:  # a terminal prompt_toolkit can't drive: plain input still works
        return None

    def read(prompt: str) -> str:
        body = prompt.lstrip("\n")
        if blank_lines := len(prompt) - len(body):
            console.print("\n" * (blank_lines - 1))
        with console.capture() as capture:  # rich markup -> ANSI colours prompt_toolkit understands
            console.print(body, end="")
        return session.prompt(ANSI(capture.get()))

    return read
