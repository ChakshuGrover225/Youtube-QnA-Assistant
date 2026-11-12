"""Naming, writing and placing the files /save-transcript creates."""

from datetime import date

import pytest

from video_summarisation_project import transcript_files
from video_summarisation_project.config import Config
from video_summarisation_project.errors import AppError
from video_summarisation_project.transcript_files import (
    choose_folder,
    clean_title,
    file_stem,
    render,
    save,
    title_from_summary,
)

DAY = date(2026, 11, 12)


@pytest.mark.parametrize(
    ("title", "stem"),
    [
        ("Job Search in Norway", "job-search-in-norway-12-11-26"),  # the example from the request
        ("Norway’s job‑search channels: Finn.no & NAV!", "norways-job-search-channels-finn-no-nav-12-11-26"),
        ("one two three four five six seven eight nine ten eleven twelve", "one-two-three-four-five-six-seven-eight-nine-ten-12-11-26"),
        ("Café crème à Paris", "café-crème-à-paris-12-11-26"),
        ("?!", "transcript-12-11-26"),
    ],
)
def test_file_stem(title, stem):
    assert file_stem(title, DAY) == stem


def test_very_long_words_are_cut_at_a_word_boundary():
    stem = file_stem(" ".join(["supercalifragilistic"] * 10), DAY)
    assert len(stem) <= 80 + len("-12-11-26")
    assert stem.endswith("supercalifragilistic-12-11-26")


@pytest.mark.parametrize(
    ("reply", "title"),
    [
        ("Job Search in Norway", "Job Search in Norway"),
        ('"Job Search in Norway."', "Job Search in Norway"),
        ("**Title:** Job Search in Norway", "Job Search in Norway"),
        ("\n\n# File name: Job Search in Norway\nBecause the video is about...", "Job Search in Norway"),
        ("", ""),
        ('""', ""),
    ],
)
def test_clean_title(reply, title):
    assert clean_title(reply) == title


@pytest.mark.parametrize(
    ("summary", "title"),
    [
        (
            "**TL;DR:** In Norway, the top job‑search channels are Finn.no, the government site arbeidsplassen.no.\n\n- Finn.no",
            "In Norway, the top job‑search channels are Finn.no, the government",
        ),
        ("TL;DR - Elephants have long trunks.", "Elephants have long trunks."),
        ("## Summary", "Summary"),
        ("", ""),
    ],
)
def test_title_from_summary(summary, title):
    assert title_from_summary(summary) == title


def test_render_has_header_summary_and_wrapped_transcript():
    transcript = " ".join(["word"] * 300)
    text = render("Job Search in Norway", "https://youtu.be/x", DAY, "TL;DR: jobs.\n", transcript)
    assert text.startswith("Job Search in Norway\nhttps://youtu.be/x\nSaved with ytchat on 12-11-2026\n\nSUMMARY\n\nTL;DR: jobs.\n\nTRANSCRIPT\n\n")
    body = text.split("TRANSCRIPT\n\n")[1]
    assert max(len(line) for line in body.splitlines()) <= 100
    assert body.split() == transcript.split()


def test_save_never_overwrites(tmp_path):
    first, written = save(tmp_path / "new folder", "jobs-12-11-26", "video A")
    assert written and first.name == "jobs-12-11-26.txt"
    again, written = save(tmp_path / "new folder", "jobs-12-11-26", "video A")
    assert (again, written) == (first, False)  # same text: already saved
    other, written = save(tmp_path / "new folder", "jobs-12-11-26", "video B")
    assert written and other.name == "jobs-12-11-26-2.txt"  # same name, different video
    assert first.read_text(encoding="utf-8") == "video A"


def test_save_reports_an_unusable_folder(tmp_path):
    (tmp_path / "file").write_text("x")
    with pytest.raises(AppError, match="Couldn't save the transcript") as caught:
        save(tmp_path / "file", "jobs-12-11-26", "text")
    assert "/change-files-save-path" in caught.value.fix


def test_default_folder_is_next_to_the_code_when_run_from_source(tmp_path, monkeypatch):
    monkeypatch.setattr(transcript_files, "_PACKAGE_DIR", tmp_path / "src" / "video_summarisation_project")
    assert transcript_files.default_save_dir() == tmp_path / "src" / "video_summarisation_project" / "saved-transcripts"


def test_default_folder_survives_a_reinstall(tmp_path, monkeypatch, isolated_config):
    # An installed copy is replaced by `uv tool install --reinstall`, so it saves next to the settings.
    monkeypatch.setattr(transcript_files, "_PACKAGE_DIR", tmp_path / "Lib" / "site-packages" / "video_summarisation_project")
    assert transcript_files.default_save_dir() == isolated_config / "saved-transcripts"


def test_a_chosen_folder_wins_over_the_default(tmp_path):
    assert transcript_files.save_dir(Config(files_save_path=str(tmp_path))) == tmp_path
    assert transcript_files.save_dir(Config()) == transcript_files.default_save_dir()


def test_choose_folder_accepts_quotes_and_relative_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder, created = choose_folder('"notes/transcripts"')
    assert (folder, created) == (tmp_path / "notes" / "transcripts", True)
    assert folder.is_dir()
    assert choose_folder(str(folder)) == (folder, False)


def test_choose_folder_expands_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert choose_folder("~/ytchat")[0] == tmp_path / "ytchat"


def test_choose_folder_rejects_a_file(tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    with pytest.raises(AppError, match="is a file, not a folder"):
        choose_folder(str(tmp_path / "notes.txt"))
