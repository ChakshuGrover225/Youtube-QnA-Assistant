"""YouTube link -> video ID -> transcript text."""

import re
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import CouldNotRetrieveTranscript, NoTranscriptFound, YouTubeTranscriptApi

from .errors import AppError

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"}
_PATH_ID_PREFIXES = {"shorts", "embed", "live", "v"}


def extract_video_id(youtube_link: str) -> str | None:
    """Return the 11-character video ID from a YouTube link, or None if it isn't one."""
    link = youtube_link.strip()
    if not link or any(ch.isspace() for ch in link):
        return None
    if "://" not in link:
        link = "https://" + link

    parsed = urlparse(link)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]

    if host == "youtu.be":
        candidate = path_parts[0] if path_parts else ""
    elif host in _YOUTUBE_HOSTS:
        if parsed.path.rstrip("/") == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif len(path_parts) >= 2 and path_parts[0] in _PATH_ID_PREFIXES:
            candidate = path_parts[1]
        else:
            candidate = ""
    else:
        return None

    return candidate if _VIDEO_ID_RE.match(candidate) else None


_TRY_ANOTHER = "Try a different video - ytchat needs one with captions (auto-generated ones are fine)."
_BLOCKED = (
    "YouTube is blocking transcript requests from your network.",
    "This happens on cloud/VPN IP addresses or after many requests. Wait a while, or try another network.",
)
# youtube-transcript-api error class name -> (problem, fix)
_TRANSCRIPT_ERRORS: dict[str, tuple[str, str]] = {
    "TranscriptsDisabled": ("Captions are turned off for this video.", _TRY_ANOTHER),
    "NoTranscriptFound": ("This video has no transcript.", _TRY_ANOTHER),
    "VideoUnavailable": (
        "This video is unavailable - it may be private, deleted, or the link may be wrong.",
        "Check that the link opens in your browser.",
    ),
    "VideoUnplayable": (
        "YouTube says this video can't be played.",
        "It may be region-locked, members-only or an upcoming premiere. Try another video.",
    ),
    "AgeRestricted": ("This video is age-restricted, so its transcript can't be fetched.", _TRY_ANOTHER),
    "InvalidVideoId": ("YouTube didn't recognise that video ID.", "Paste the full link from your browser's address bar."),
    "RequestBlocked": _BLOCKED,
    "IpBlocked": _BLOCKED,
    "PoTokenRequired": ("YouTube asked for extra verification to get this transcript.", "Try again later, or try another video."),
    "YouTubeRequestFailed": ("The request to YouTube failed.", "Check your internet connection and try again."),
}


def fetch_transcript(video_id: str, languages: list[str]) -> str:
    """Return the video's transcript as plain text, preferring `languages` in order."""
    try:
        transcripts = YouTubeTranscriptApi().list(video_id)
        try:
            transcript = transcripts.find_transcript(languages)
        except NoTranscriptFound:
            # None in the preferred languages - fall back to whatever exists.
            transcript = next(iter(transcripts), None)
            if transcript is None:
                raise
        fetched = transcript.fetch()
    except CouldNotRetrieveTranscript as exc:
        problem, fix = _TRANSCRIPT_ERRORS.get(
            type(exc).__name__,
            (f"Couldn't get a transcript for this video ({type(exc).__name__}).", _TRY_ANOTHER),
        )
        raise AppError(problem, fix, kind="input") from exc
    except OSError as exc:  # requests' network errors are OSErrors
        raise AppError(
            f"Couldn't reach YouTube ({type(exc).__name__}).",
            "Check your internet connection and try again.",
            kind="network",
        ) from exc

    text = " ".join(snippet.text.replace("\n", " ") for snippet in fetched).strip()
    if not text:
        raise AppError("This video's transcript is empty.", _TRY_ANOTHER, kind="input")
    return text
