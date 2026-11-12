"""/save-transcript: the open video's transcript (and summary) as a text file.

Files are named "<short-title>-<dd-mm-yy>.txt", e.g. job-search-in-norway-12-11-26.txt,
and go in the folder picked with /change-files-save-path (config.files_save_path).
The title is written by the chat model in cli.py; this module does everything else.
"""

from __future__ import annotations

import itertools
import os
import re
import textwrap
from datetime import date
from pathlib import Path

from .config import Config, config_dir
from .errors import AppError
from .safe_text import printable

MAX_TITLE_WORDS = 10
_MAX_STEM_CHARS = 80  # keeps full paths well under Windows' 260-character limit
_WRAP_WIDTH = 100

_PACKAGE_DIR = Path(__file__).resolve().parent


def default_save_dir() -> Path:
    """`saved-transcripts/` next to this code when ytchat runs from the project folder.

    An installed copy (`uv tool install .`) lives in a tool environment that is deleted
    on every reinstall, so it saves next to the settings file instead.
    """
    if {"site-packages", "dist-packages"} & set(_PACKAGE_DIR.parts):
        return config_dir() / "saved-transcripts"
    return _PACKAGE_DIR / "saved-transcripts"


def save_dir(config: Config) -> Path:
    return Path(config.files_save_path) if config.files_save_path else default_save_dir()


def choose_folder(text: str) -> tuple[Path, bool]:
    """A folder the user typed -> (absolute path, whether it had to be created). Raises AppError."""
    raw = text.strip().strip("'\"").strip()
    example = "e.g. /change-files-save-path ~/Documents/ytchat"
    try:
        folder = Path(os.path.expandvars(raw)).expanduser().resolve()  # relative = from the current folder
        if folder.exists() and not folder.is_dir():
            raise AppError(f"{folder} is a file, not a folder.", f"Give the path of a folder, {example}", kind="input")
        existed = folder.is_dir()
        folder.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        reason = getattr(exc, "strerror", None) or exc
        raise AppError(f"Couldn't use the folder {raw} ({reason}).", f"Check the path, {example}", kind="input") from exc
    return folder, not existed


def clean_title(reply: str) -> str:
    """The first line of the model's answer, without quotes, Markdown or a 'Title:' label."""
    junk = " \t#*_`\"'“”‘’"
    for line in reply.splitlines():
        line = re.sub(r"^(?:title|file ?name)\s*:\s*", "", line.strip(junk), flags=re.IGNORECASE)
        if line := line.strip(junk + "."):
            return line
    return ""


def title_from_summary(summary: str) -> str:
    """The first words of the summary's TL;DR line, for when the model can't name the file."""
    for line in summary.splitlines():
        line = re.sub(r"^[\s#*_>-]*(?:tl;?dr\b)?[\s*_:-]*", "", line, flags=re.IGNORECASE).strip()
        if line:
            return " ".join(line.split()[:MAX_TITLE_WORDS])
    return ""


def file_stem(title: str, day: date) -> str:
    """'Job Search in Norway' -> 'job-search-in-norway-12-11-26'."""
    words = re.findall(r"[^\W_]+", re.sub(r"['’]", "", title).lower())  # letters and digits, any script
    slug = "-".join(words[:MAX_TITLE_WORDS])
    if len(slug) > _MAX_STEM_CHARS:
        slug = slug[:_MAX_STEM_CHARS].rsplit("-", 1)[0]
    return f"{slug or 'transcript'}-{day:%d-%m-%y}"


def render(title: str, link: str, day: date, summary: str, transcript: str) -> str:
    """The file's text: a short header, the summary, then the transcript wrapped into lines.

    Everything is cleaned of terminal control characters, so printing the file
    (`type`, `cat`) can't run escape sequences hidden in a transcript or reply.
    """
    title, summary, transcript = printable(title), printable(summary), printable(transcript)
    wrapped = textwrap.fill(" ".join(transcript.split()), _WRAP_WIDTH, break_long_words=False, break_on_hyphens=False)
    return (
        f"{title}\n{link}\nSaved with ytchat on {day:%d-%m-%Y}\n\n"
        f"SUMMARY\n\n{summary.strip()}\n\n"
        f"TRANSCRIPT\n\n{wrapped}\n"
    )


def save(folder: Path, stem: str, text: str) -> tuple[Path, bool]:
    """Write `text` to <folder>/<stem>.txt -> (path, whether a new file was written).

    Never overwrites: a file that already holds the same text counts as saved, and a
    different file with the same name (another video, same title, same day) gets -2, -3...
    """
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for n in itertools.count(1):
            path = folder / (f"{stem}.txt" if n == 1 else f"{stem}-{n}.txt")
            try:
                with path.open("x", encoding="utf-8") as file:
                    file.write(text)
                return path, True
            except FileExistsError:
                if path.is_file() and path.read_text(encoding="utf-8", errors="replace") == text:
                    return path, False
    except OSError as exc:
        raise AppError(
            f"Couldn't save the transcript in {folder} ({exc.strerror or exc}).",
            "Pick a folder you can write to with /change-files-save-path.",
            kind="config",
        ) from exc
    raise AssertionError("unreachable")
