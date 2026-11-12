import pytest

from video_summarisation_project.youtube_transcription import extract_video_id


@pytest.mark.parametrize(
    "link",
    [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtube.com/watch?v=jNQXAC9IVRw&t=10s",
        "youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtu.be/jNQXAC9IVRw?si=abc",
        "https://m.youtube.com/watch?v=jNQXAC9IVRw",
        "https://www.youtube.com/shorts/jNQXAC9IVRw",
        "https://www.youtube.com/embed/jNQXAC9IVRw",
        "https://www.youtube.com/live/jNQXAC9IVRw",
    ],
)
def test_valid_links(link):
    assert extract_video_id(link) == "jNQXAC9IVRw"


@pytest.mark.parametrize(
    "text",
    [
        "", "hello there", "What is this video about?", "https://vimeo.com/123", "https://youtube.com/watch?v=short", "https://youtube.com/",
        "https://notyoutube.com/watch?v=jNQXAC9IVRw", "x[0]?", "a[b",  # brackets used to crash urlparse
    ],
)
def test_not_links(text):
    assert extract_video_id(text) is None
