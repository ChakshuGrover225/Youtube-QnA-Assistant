"""Groq speech-to-text, run against a mocked HTTP transport (no network, no real key)."""

import json

import groq
import httpx
import pytest

from video_summarisation_project import speech_to_text
from video_summarisation_project.config import Config, load_config
from video_summarisation_project.errors import AppError
from video_summarisation_project.speech_to_text import _http_error, transcribe

KEY = "gsk_test_key_1234567890"
SPEECH = "  Hello there,\n this reel is about   learning AI with fewer tabs open. "


def mock_groq(status=200, body=None):
    """An http_client whose every request gets the given response; sent requests are in .requests."""
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json=body if body is not None else {"text": SPEECH})

    client = groq.DefaultHttpxClient(transport=httpx.MockTransport(handler))
    client.requests = requests
    return client


@pytest.fixture
def audio(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    path = tmp_path / "audio.m4a"
    path.write_bytes(b"fake m4a bytes")
    return path


def test_request_shape_and_cleaned_text(audio):
    http = mock_groq()
    text = transcribe(audio, Config(vendor="anthropic"), http_client=http)
    assert text == "Hello there, this reel is about learning AI with fewer tabs open."

    (request,) = http.requests
    assert request.method == "POST" and request.url.path.endswith("/audio/transcriptions")
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = request.read()
    assert b'name="model"' in body and b"whisper-large-v3-turbo" in body
    assert b'filename="audio.m4a"' in body and b"fake m4a bytes" in body
    assert b'name="language"' not in body  # the language is detected, not forced


def test_saved_key_and_model_are_used(audio):
    config = Config()
    config.settings_for("groq").api_key = "gsk_saved_key_0987654321"
    config.transcription_model = "whisper-large-v3"
    http = mock_groq()
    transcribe(audio, config, http_client=http)
    request = http.requests[0]
    assert request.headers["authorization"] == "Bearer gsk_saved_key_0987654321"
    assert b"whisper-large-v3\r\n" in request.read()


def test_missing_key_sends_nothing(audio, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    http = mock_groq()
    with pytest.raises(AppError) as caught:
        transcribe(audio, Config(), http_client=http)
    assert caught.value.kind == "config" and "/add-api-key groq" in caught.value.fix
    assert http.requests == []


def test_rejected_key(audio):
    http = mock_groq(401, {"error": {"message": "Invalid API Key"}})
    with pytest.raises(AppError) as caught:
        transcribe(audio, Config(), http_client=http)
    assert caught.value.kind == "auth"
    assert caught.value.problem == "Groq rejected your API key (Invalid API Key)."
    assert "/add-api-key groq" in caught.value.fix


@pytest.mark.parametrize("heard", ["", "Thank you.", "♪ ♪ ♪"])
def test_no_speech(audio, heard):
    with pytest.raises(AppError) as caught:
        transcribe(audio, Config(), http_client=mock_groq(body={"text": heard}))
    assert caught.value.kind == "input"
    assert caught.value.problem.startswith("There's too little speech in this reel to chat about")
    if heard:
        assert f'all it heard was "{heard}"' in caught.value.problem


def test_too_large_audio_is_not_uploaded(audio, monkeypatch):
    monkeypatch.setattr(speech_to_text, "MAX_UPLOAD_BYTES", 5)
    http = mock_groq()
    with pytest.raises(AppError) as caught:
        transcribe(audio, Config(), http_client=http)
    assert caught.value.kind == "limit" and "too large" in caught.value.problem
    assert http.requests == []


@pytest.mark.parametrize(
    ("status", "detail", "kind", "problem"),
    [
        (404, "The model `whisper-x` does not exist", "model", "Groq doesn't offer the speech-to-text model 'whisper-x'"),
        (413, "Request Entity Too Large", "limit", "too large for Groq to transcribe"),
        (429, "Rate limit reached", "limit", "rate limit or quota reached"),
        (503, "Service Unavailable", "network", "having problems right now"),
        (400, "file must be one of the following types", "other", "couldn't transcribe this reel's audio"),
    ],
)
def test_http_errors(status, detail, kind, problem):
    error = _http_error(status, detail, "whisper-x")
    assert error.kind == kind and problem in error.problem


def test_model_error_points_at_the_setting():
    assert "transcription_model" in _http_error(404, "not found", "whisper-x").fix


def test_old_config_without_the_setting_still_loads(isolated_config):
    isolated_config.mkdir(parents=True)
    (isolated_config / "config.json").write_text(json.dumps({"vendor": "anthropic"}), encoding="utf-8")
    assert load_config().transcription_model == "whisper-large-v3-turbo"
