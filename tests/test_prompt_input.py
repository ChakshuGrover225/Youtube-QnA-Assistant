"""Slash-command suggestions at the main prompt."""

import io
import threading
import time

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from video_summarisation_project import cli, prompt_input
from video_summarisation_project.cli import COMMANDS
from video_summarisation_project.config import Config
from video_summarisation_project.prompt_input import SlashCommandCompleter, make_session, terminal_reader


def suggestions(text):
    completions = SlashCommandCompleter(COMMANDS).get_completions(Document(text), CompleteEvent(text_inserted=True))
    return [c.text for c in completions]


def test_slash_lists_every_command_in_help_order():
    assert suggestions("/") == list(COMMANDS)


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("/s", ["/save-transcript"]),
        ("/c", ["/change-model", "/change-vendor", "/config", "/change-files-save-path"]),
        ("/change-", ["/change-model", "/change-vendor", "/change-files-save-path"]),
        ("/CH", ["/change-model", "/change-vendor", "/change-files-save-path"]),
        ("  /n", ["/new"]),
        ("/new", ["/new"]),
        ("/x", []),
    ],
)
def test_only_commands_starting_with_what_was_typed(typed, expected):
    assert suggestions(typed) == expected


@pytest.mark.parametrize(
    "typed",
    ["", "what does she say?", "https://youtu.be/jkOUMFaLVGo", "/change-model gpt", "/add-api-key "],
)
def test_no_suggestions_for_questions_links_or_arguments(typed):
    assert suggestions(typed) == []


def test_suggestions_show_usage_and_description():
    [completion] = SlashCommandCompleter(COMMANDS).get_completions(Document("/change-v"), CompleteEvent())
    assert completion.display_text == "/change-vendor [name]"
    assert completion.display_meta_text == COMMANDS["/change-vendor"][1]
    assert completion.start_position == -len("/change-v")  # replaces what was typed


def typed(*keystrokes):
    """Run a real prompt, typing each group of keys with a pause like a person would.

    Suggestions are worked out in the background, so keys sent all at once can arrive first.
    """
    with create_pipe_input() as keys:
        def type_slowly():
            for text in keystrokes:
                time.sleep(0.2)
                keys.send_text(text)

        threading.Thread(target=type_slowly, daemon=True).start()
        return make_session(COMMANDS, input=keys, output=DummyOutput()).prompt("You › ")


DOWN = "\x1b[B"


@pytest.mark.parametrize(
    ("keystrokes", "line"),
    [
        (("/s", "\t", "\r"), "/save-transcript"),  # Tab picks the suggestion, one Enter runs it
        (("/c", "\t", "\t", "\r"), "/change-vendor"),  # Tab again moves to the next one
        (("/c", DOWN, "\r"), "/change-model"),  # arrow keys work too
        (("/change-model gpt-oss-20b", "\r"), "/change-model gpt-oss-20b"),  # typing on ignores them
        (("https://youtu.be/jkOUMFaLVGo", "\r"), "https://youtu.be/jkOUMFaLVGo"),
    ],
)
def test_picking_suggestions_in_a_real_prompt(keystrokes, line):
    assert typed(*keystrokes) == line


def test_plain_input_when_not_in_a_terminal():
    # pytest's stdin isn't a terminal, like a pipe
    assert terminal_reader(Console(file=io.StringIO()), COMMANDS) is None


def test_terminal_reader_shows_the_coloured_prompt(monkeypatch):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    prompts = []

    class FakeSession:
        def prompt(self, message):
            prompts.append(message)
            return "/help"

    monkeypatch.setattr(prompt_input.sys, "stdin", Terminal())
    monkeypatch.setattr(prompt_input.sys, "stdout", Terminal())
    monkeypatch.setattr(prompt_input, "make_session", lambda commands: FakeSession())
    out = io.StringIO()
    read = terminal_reader(Console(file=out, force_terminal=True, color_system="standard"), COMMANDS)
    assert read("\n[bold green]You ›[/] ") == "/help"
    assert out.getvalue() == "\n"  # the blank line before the prompt
    [message] = prompts
    assert message.value == "\x1b[1;32mYou ›\x1b[0m "  # rich markup became ANSI colours


def test_app_reads_the_main_prompt_with_the_reader_and_questions_with_console_input():
    console = Console(file=io.StringIO(), width=120, color_system=None)
    main_prompts, asked = [], []
    lines = ["/change-vendor", "/exit"]

    def read_line(prompt):
        main_prompts.append(prompt)
        return lines.pop(0)

    def fake_input(prompt="", password=False):
        asked.append(prompt)
        return ""  # Enter: vendor not changed

    console.input = fake_input
    cli.App(console, Config(), read_line).run()
    assert len(main_prompts) == 2 and "Video link ›" in main_prompts[0]
    assert len(asked) == 1 and "Vendor (name or number)" in asked[0]
