"""Telling links from questions, and routing each link to its platform's transcript code."""

import pytest

from video_summarisation_project import link_classifier, youtube_transcription
from video_summarisation_project.config import Config
from video_summarisation_project.link_classifier import PLATFORMS, Platform, VideoLink, classify, get_transcript


@pytest.mark.parametrize(
    ("link", "platform", "video_id"),
    [
        ("https://www.youtube.com/watch?v=jkOUMFaLVGo", "youtube", "jkOUMFaLVGo"),
        ("https://youtu.be/jkOUMFaLVGo", "youtube", "jkOUMFaLVGo"),
        ("https://youtube.com/shorts/gB7Gjp2fK8U", "youtube", "gB7Gjp2fK8U"),
        ("https://www.youtube.com/shorts/1XRXRIYMczM", "youtube", "1XRXRIYMczM"),
        ("https://www.instagram.com/reels/DflaaesxV7S/", "instagram", "DflaaesxV7S"),
        ("https://www.instagram.com/reel/DflaaesxV7S/?rpxt=NTc4MTIwNjQ2YQ==", "instagram", "DflaaesxV7S"),
    ],
)
def test_links_are_classified(link, platform, video_id):
    video = classify(link)
    assert video is not None
    assert (video.platform.name, video.id) == (platform, video_id)


@pytest.mark.parametrize(
    "text",
    ["What does she say about Replit?", "x[0]?", "youtube.com", "instagram.com/reel/", "https://vimeo.com/123"],
)
def test_questions_and_other_links_are_not_classified(text):
    assert classify(text) is None


def test_no_link_is_claimed_by_two_platforms():
    links = ["https://youtu.be/jkOUMFaLVGo", "https://www.instagram.com/reel/DflaaesxV7S/"]
    for link in links:
        assert sum(platform.parse(link) is not None for platform in PLATFORMS) == 1


def test_youtube_uses_the_preferred_languages(monkeypatch):
    calls = []
    monkeypatch.setattr(youtube_transcription, "fetch_transcript", lambda video_id, languages: calls.append((video_id, languages)) or "text")
    video = classify("https://youtu.be/jkOUMFaLVGo")
    assert get_transcript(video, Config(transcript_languages=["hi", "en"])) == "text"
    assert calls == [("jkOUMFaLVGo", ["hi", "en"])]


def test_get_transcript_routes_to_the_platform_with_progress():
    fake = Platform("fake", "clip", lambda link: None, lambda video_id, config, progress: progress("working") or f"transcript of {video_id}", link_format="https://fake/{id}")
    progress = []
    assert get_transcript(VideoLink(fake, "abc"), Config(), progress.append) == "transcript of abc"
    assert progress == ["working"]


def test_get_transcript_works_without_a_progress_callback():
    fake = Platform("fake", "clip", lambda link: None, lambda video_id, config, progress: progress("ignored") or "ok", link_format="https://fake/{id}")
    assert link_classifier.get_transcript(VideoLink(fake, "abc"), Config()) == "ok"
