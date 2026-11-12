"""Instagram Reel link -> shortcode -> audio (downloaded with yt-dlp) -> transcript text.

Reels have no captions to fetch, so the reel's audio is downloaded into a temporary
folder, transcribed by speech_to_text (Groq Whisper), and deleted again. Only public
reels work: ytchat never logs in to Instagram.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from . import speech_to_text
from .config import Config
from .errors import AppError

_HOSTS = {"instagram.com", "m.instagram.com"}
_REEL_PATHS = {"reel", "reels"}
_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,64}$")


def extract_reel_shortcode(link: str) -> str | None:
    """The shortcode from an Instagram Reel link, or None if it isn't one. No network, never raises."""
    link = link.strip()
    if not link or any(ch.isspace() for ch in link):
        return None
    if "://" not in link:
        link = "https://" + link

    try:
        parsed = urlparse(link)
        host = (parsed.hostname or "").lower().removeprefix("www.")
    except ValueError:  # e.g. "x[0]?" reads as a malformed IPv6 address
        return None
    if host not in _HOSTS:
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) == 3:  # instagram.com/<username>/reel/<shortcode>/, as shared from a profile
        parts = parts[1:]
    if len(parts) != 2 or parts[0].lower() not in _REEL_PATHS:
        return None
    return parts[1] if _SHORTCODE_RE.match(parts[1]) else None


# --- Download -----------------------------------------------------------------


class _Silent:
    """Keeps yt-dlp's own messages off the terminal; failures arrive as exceptions instead."""

    def debug(self, msg: str) -> None:
        pass

    info = warning = error = debug


_YT_DLP_PREFIX = re.compile(r"^(?:ERROR:\s*)?(?:\[\w+\]\s*[\w-]+:\s*)?")


def _download_error(message: str) -> AppError:
    """Turn a yt-dlp error message into a problem + fix."""
    detail = _YT_DLP_PREFIX.sub("", message.strip())
    short = detail.split(". ")[0][:200]
    low = detail.lower()
    # Private, deleted and login-only reels all come back as an "empty media response".
    if "empty media response" in low or "login" in low or "cookies" in low:
        return AppError(
            "Instagram didn't return this reel - it may be private, deleted, or only visible when logged in.",
            "ytchat can only open public reels. Check that the link opens in a private (incognito) browser window; "
            "if it does, Instagram may be limiting requests from your network - wait a while and try again.",
            kind="input",
        )
    if "429" in low or "too many requests" in low:
        return AppError("Instagram is limiting requests from your network.", "Wait a while and try again, or try another network.", kind="limit")
    if "404" in low or "not found" in low or "not available" in low:
        return AppError(
            "This reel is unavailable - it may have been deleted, or the link may be wrong.",
            "Check that the link opens in your browser.",
            kind="input",
        )
    if "no video" in low:
        return AppError("This post has no video to transcribe.", "Paste a link to a reel.", kind="input")
    if any(s in low for s in ("unable to download", "timed out", "connection", "getaddrinfo", "urlopen", "transporterror", "ssl")):
        return AppError(
            f"Couldn't reach Instagram ({short}).",
            "Check your internet connection (and any proxy or VPN), then try again.",
            kind="network",
        )
    return AppError(
        f"Couldn't download this reel ({short}).",
        "If other public reels fail too, Instagram may have changed its site and a newer yt-dlp is needed: "
        "follow \"Updating yt-dlp\" in the README (it updates yt-dlp only, never every dependency).",
    )


def download_audio(shortcode: str, folder: Path) -> Path:
    """Download the reel's audio into `folder` and return the file. Raises AppError."""
    options = {
        # The audio-only stream if there is one, else a video file with sound. Groq
        # accepts both as they are, so ffmpeg isn't needed.
        "format": "bestaudio[ext=m4a]/bestaudio/best[ext=mp4]/best",
        "outtmpl": str(folder / "audio.%(ext)s"),
        "logger": _Silent(),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([f"https://www.instagram.com/reel/{shortcode}/"])
    except yt_dlp.utils.YoutubeDLError as exc:
        raise _download_error(str(exc)) from exc

    saved = [p for p in folder.glob("audio.*") if p.suffix not in (".part", ".ytdl")]
    if not saved:
        raise _download_error("the download finished without saving an audio file")
    return saved[0]


def fetch_reel_transcript(shortcode: str, config: Config, progress: Callable[[str], object]) -> str:
    """Download the reel's audio, transcribe it, and delete the audio again. Raises AppError."""
    speech_to_text.require_groq_key(config)  # setup problems show up before anything is downloaded
    with tempfile.TemporaryDirectory(prefix="ytchat-", ignore_cleanup_errors=True) as folder:
        progress("Downloading the reel's audio...")
        audio = download_audio(shortcode, Path(folder))
        progress(f"Transcribing with Groq · {config.transcription_model}...")
        return speech_to_text.transcribe(audio, config)
