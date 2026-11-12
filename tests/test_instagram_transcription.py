"""Instagram Reel links, the yt-dlp download (faked) and the download -> transcribe pipeline."""

from pathlib import Path

import pytest
import yt_dlp

from video_summarisation_project import instagram_transcription, speech_to_text
from video_summarisation_project.config import Config
from video_summarisation_project.errors import AppError
from video_summarisation_project.instagram_transcription import (
    _download_error,
    download_audio,
    extract_reel_shortcode,
    fetch_reel_transcript,
)

CODE = "DflaaesxV7S"


@pytest.mark.parametrize(
    "link",
    [
        f"https://www.instagram.com/reel/{CODE}/",
        f"https://www.instagram.com/reels/{CODE}/",
        f"https://www.instagram.com/reel/{CODE}/?rpxt=NTc4MTIwNjQ2YQ==",
        f"https://www.instagram.com/reel/{CODE}/?igsh=MWQ1ZGUxMzBkMA==",
        f"https://www.instagram.com/reel/{CODE}",
        f"instagram.com/reel/{CODE}/",
        f"http://instagram.com/reel/{CODE}/",
        f"https://m.instagram.com/reel/{CODE}/",
        f"https://WWW.Instagram.com/reel/{CODE}/",
        f"https://www.instagram.com/techbyruchi/reel/{CODE}/",
        f"https://www.instagram.com/reel/{CODE}/#comments",
        f"  https://www.instagram.com/reel/{CODE}/  ",
    ],
)
def test_reel_links(link):
    assert extract_reel_shortcode(link) == CODE


@pytest.mark.parametrize(
    "text",
    [
        "",
        "What is this reel about?",
        "x[0]?",
        "a[b",
        "https://www.instagram.com/",
        "https://www.instagram.com/techbyruchi/",
        "https://www.instagram.com/reel/",
        "https://www.instagram.com/stories/techbyruchi/1234567890/",
        "https://www.instagram.com/reels/audio/1234567890/",
        f"https://www.instagram.com/p/{CODE}/",  # posts may be images: only reels are accepted
        f"https://www.notinstagram.com/reel/{CODE}/",
        f"https://instagram.com.evil.example/reel/{CODE}/",
        f"https://www.instagram.com/reel/{CODE}/ and more",
        "https://www.instagram.com/reel/a+b/",
        "https://youtu.be/jNQXAC9IVRw",
    ],
)
def test_not_reel_links(text):
    assert extract_reel_shortcode(text) is None


# --- yt-dlp errors ---------------------------------------------------------------

EMPTY_MEDIA = (
    f"ERROR: [Instagram] {CODE}: Instagram sent an empty media response. Check if this post is accessible in your "
    "browser without being logged-in. If it is not, then use --cookies-from-browser or --cookies for the authentication."
)


@pytest.mark.parametrize(
    ("message", "kind", "problem"),
    [
        (EMPTY_MEDIA, "input", "may be private, deleted, or only visible when logged in"),
        (f"ERROR: [Instagram] {CODE}: Requested content is not available, rate-limit reached or login required", "input", "only visible when logged in"),
        (f"ERROR: [Instagram] {CODE}: Unable to download webpage: HTTP Error 429: Too Many Requests", "limit", "limiting requests"),
        (f"ERROR: [Instagram] {CODE}: Unable to download webpage: HTTP Error 404: Not Found", "input", "This reel is unavailable"),
        (f"ERROR: [Instagram] {CODE}: There is no video in this post", "input", "no video"),
        (f"ERROR: [Instagram] {CODE}: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>", "network", "Couldn't reach Instagram"),
        (f"ERROR: [Instagram] {CODE}: Unable to extract shared data; please report this issue", "other", "Couldn't download this reel (Unable to extract shared data"),
    ],
)
def test_download_errors_are_translated(message, kind, problem):
    error = _download_error(message)
    assert error.kind == kind
    assert problem in error.problem
    assert "ERROR:" not in error.problem and "[Instagram]" not in error.problem


def test_unknown_download_error_says_how_to_update():
    fix = _download_error("ERROR: something new").fix
    assert "Updating yt-dlp" in fix
    assert "--upgrade" not in fix  # never advise upgrading every dependency at once


class FakeYoutubeDL:
    """Stands in for yt_dlp.YoutubeDL: records the options and 'downloads' a small file."""

    calls: list = []
    fail: Exception | None = None

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def download(self, urls):
        FakeYoutubeDL.calls.append((self.options, urls))
        if FakeYoutubeDL.fail:
            raise FakeYoutubeDL.fail
        Path(self.options["outtmpl"].replace("%(ext)s", "m4a")).write_bytes(b"fake audio")
        return 0


@pytest.fixture
def fake_ytdl(monkeypatch):
    FakeYoutubeDL.calls, FakeYoutubeDL.fail = [], None
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    return FakeYoutubeDL


def test_download_audio_asks_for_audio_only_without_ffmpeg(fake_ytdl, tmp_path):
    audio = download_audio(CODE, tmp_path)
    assert audio == tmp_path / "audio.m4a" and audio.read_bytes() == b"fake audio"
    options, urls = fake_ytdl.calls[0]
    assert urls == [f"https://www.instagram.com/reel/{CODE}/"]  # tracking parameters never reach Instagram
    assert options["format"].startswith("bestaudio[ext=m4a]")
    assert "postprocessors" not in options  # nothing that needs ffmpeg
    assert "cookiefile" not in options and "cookiesfrombrowser" not in options  # public reels only


def test_download_audio_translates_yt_dlp_errors(fake_ytdl, tmp_path):
    fake_ytdl.fail = yt_dlp.utils.DownloadError(EMPTY_MEDIA)
    with pytest.raises(AppError) as caught:
        download_audio(CODE, tmp_path)
    assert caught.value.kind == "input" and "private" in caught.value.problem


# --- The whole pipeline ----------------------------------------------------------


def test_missing_groq_key_stops_before_downloading(fake_ytdl):
    with pytest.raises(AppError) as caught:
        fetch_reel_transcript(CODE, Config(vendor="anthropic"), print)
    assert caught.value.kind == "config"
    assert "no Groq API key is saved" in caught.value.problem
    assert "/add-api-key groq" in caught.value.fix
    assert fake_ytdl.calls == []


@pytest.fixture
def temp_folders(monkeypatch, tmp_path):
    """Puts the pipeline's temporary folders under tmp_path, so the test can check they're gone."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_1234567890")
    root = tmp_path / "temp"
    root.mkdir()
    monkeypatch.setattr(instagram_transcription.tempfile, "tempdir", str(root))
    return root


def test_reel_transcript_and_temp_folder_is_deleted(fake_ytdl, temp_folders, monkeypatch):
    seen = []

    def fake_transcribe(audio, config):
        seen.append(audio.read_bytes())
        return "hello from the reel"

    monkeypatch.setattr(speech_to_text, "transcribe", fake_transcribe)
    progress = []
    assert fetch_reel_transcript(CODE, Config(), progress.append) == "hello from the reel"
    assert seen == [b"fake audio"]
    assert progress == ["Downloading the reel's audio...", "Transcribing with Groq · whisper-large-v3-turbo..."]
    assert list(temp_folders.iterdir()) == []


@pytest.mark.parametrize("failure", [AppError("Groq rate limit", kind="limit"), KeyboardInterrupt()])
def test_temp_folder_is_deleted_after_a_failure(fake_ytdl, temp_folders, monkeypatch, failure):
    def failing_transcribe(audio, config):
        assert audio.exists()
        raise failure

    monkeypatch.setattr(speech_to_text, "transcribe", failing_transcribe)
    with pytest.raises(type(failure)):
        fetch_reel_transcript(CODE, Config(), lambda _: None)
    assert list(temp_folders.iterdir()) == []
