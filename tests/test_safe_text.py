"""Terminal control characters are removed from outside text; everything readable is kept."""

import pytest

from video_summarisation_project.errors import AppError
from video_summarisation_project.safe_text import printable


@pytest.mark.parametrize(
    ("text", "clean"),
    [
        ("clear\x1b[2Jscreen", "clear[2Jscreen"),  # ESC removed: the rest is harmless text
        ("title\x1b]0;owned\x07", "title]0;owned"),  # window-title sequence
        ("clip\x1b]52;c;Y3VybA==\x1b\\", "clip]52;c;Y3VybA==\\"),  # clipboard write (OSC 52)
        ("one-byte\x9b2J", "one-byte2J"),  # C1 "CSI"
        ("bell\x07 null\x00 del\x7f back\x08", "bell null del back"),
        ("abc‮dcba", "abcdcba"),  # right-to-left override
        ("lines\r\nkept\ttabs", "lines\nkept\ttabs"),
    ],
)
def test_control_characters_are_removed(text, clean):
    assert printable(text) == clean


def test_readable_text_is_untouched():
    text = "Norway’s job‑search: Finn.no — 243,000 ads 👩‍💻 नमस्ते العربية\n- bullet\n\tindented"
    assert printable(text) == text  # incl. the zero-width joiner inside the emoji


def test_app_errors_are_cleaned_once_for_every_place_they_are_printed():
    error = AppError("Groq said \x1b[31mno\x1b[0m", "Check \x1b]0;x\x07it")
    assert error.problem == "Groq said [31mno[0m"
    assert error.fix == "Check ]0;xit"
    assert str(error) == error.problem
    assert AppError("fine").fix is None
