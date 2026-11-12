"""Which platform a link belongs to, and the one call that turns it into a transcript.

Each platform lives in its own `<platform>_transcription.py` module, which provides:

- a link parser: link -> ID, or None if the link isn't for that platform. It must be
  fast, make no network calls and never raise, because cli.py runs it on every line
  the user types to tell new links from questions.
- a fetcher: ID -> transcript text. It may be slow, and raises only AppError.

To add a platform, write its module and add one entry to PLATFORMS.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import instagram_transcription, youtube_transcription
from .config import Config

# Receives a short status line ("Downloading the reel's audio...") while a slow fetch runs.
Progress = Callable[[str], object]


@dataclass(frozen=True)
class Platform:
    name: str  # "youtube", "instagram"
    noun: str  # what the platform calls a video, used in titles: "video", "reel"
    parse: Callable[[str], str | None]
    fetch: Callable[[str, Config, Progress], str]
    link_format: str  # the clean link for an ID, e.g. "https://youtu.be/{id}"


@dataclass(frozen=True)
class VideoLink:
    """A link the user pasted, after classification."""

    platform: Platform
    id: str

    @property
    def url(self) -> str:
        """The link without tracking parameters (?si=, ?igsh=...)."""
        return self.platform.link_format.format(id=self.id)


def _fetch_youtube(video_id: str, config: Config, progress: Progress) -> str:
    return youtube_transcription.fetch_transcript(video_id, config.transcript_languages)


# Tried in order: the first platform whose parser accepts the link handles it.
PLATFORMS: tuple[Platform, ...] = (
    Platform(
        "youtube", "video", youtube_transcription.extract_video_id, _fetch_youtube,
        link_format="https://www.youtube.com/watch?v={id}",
    ),
    Platform(
        "instagram", "reel", instagram_transcription.extract_reel_shortcode, instagram_transcription.fetch_reel_transcript,
        link_format="https://www.instagram.com/reel/{id}/",
    ),
)


def classify(text: str) -> VideoLink | None:
    """The platform and ID for a supported link, or None if `text` isn't one."""
    for platform in PLATFORMS:
        if video_id := platform.parse(text):
            return VideoLink(platform, video_id)
    return None


def _no_progress(_status: str) -> None:
    pass


def get_transcript(video: VideoLink, config: Config, progress: Progress = _no_progress) -> str:
    """The transcript text for a classified link. Raises AppError."""
    return video.platform.fetch(video.id, config, progress)
