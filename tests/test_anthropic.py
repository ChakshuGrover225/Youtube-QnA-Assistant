"""The Anthropic request shape, checked against a mocked HTTP transport (no key or network needed)."""

import json

import anthropic
import httpx2
import pytest

from video_summarisation_project.config import Config
from video_summarisation_project.errors import AppError
from video_summarisation_project.vendors import AnthropicBackend, Turn


def _message(content, stop_reason="end_turn", stop_details=None, model="claude-opus-5-5"):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_details": stop_details,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _backend(model, *responses):
    sent = []
    queue = list(responses)

    def handler(request):
        sent.append(request)
        status, body = queue.pop(0)
        return httpx2.Response(status, json=body)

    client = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    return AnthropicBackend(model, Config(), "sk-ant-test-key-123456", http_client=client), sent


def test_request_shape_and_thinking_replay():
    first = _message([{"type": "thinking", "thinking": "", "signature": "sig-1"}, {"type": "text", "text": "Summary"}])
    second = _message([{"type": "text", "text": "Answer"}])
    backend, sent = _backend("claude-opus-5-5", (200, first), (200, second))

    turns = [Turn("user", "Summarise this video.")]
    reply = backend.chat("SYSTEM + transcript", turns)
    assert reply.text == "Summary"

    body = json.loads(sent[0].content)
    assert body["model"] == "claude-opus-5-5"
    assert body["system"] == "SYSTEM + transcript"
    assert body["max_tokens"] == AnthropicBackend.DEFAULT_MAX_TOKENS
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["fallbacks"] == "default"
    assert AnthropicBackend.FALLBACK_BETA in sent[0].headers["anthropic-beta"]
    assert "temperature" not in body  # current Claude models reject it

    # The next request replays the assistant turn's blocks unchanged, thinking included.
    turns += [Turn("assistant", reply.text, raw=reply.raw, raw_vendor="anthropic"), Turn("user", "And then?")]
    assert backend.chat("SYSTEM + transcript", turns).text == "Answer"
    replayed = json.loads(sent[1].content)["messages"][1]
    assert replayed["role"] == "assistant"
    assert replayed["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig-1"}


def test_turns_from_other_vendors_are_sent_as_text():
    backend, sent = _backend("claude-haiku-5-5", (200, _message([{"type": "text", "text": "ok"}], model="claude-haiku-5-5")))
    turns = [Turn("user", "Q1"), Turn("assistant", "A1 from groq", raw_vendor="groq"), Turn("user", "Q2")]
    backend.chat("S", turns)
    body = json.loads(sent[0].content)
    assert body["messages"][1] == {"role": "assistant", "content": "A1 from groq"}
    assert "fallbacks" not in body  # only sent to models that support it


def test_refusal_becomes_an_app_error():
    refused = _message([], stop_reason="refusal", stop_details={"type": "refusal", "category": "cyber", "explanation": None})
    backend, _ = _backend("claude-opus-5-5", (200, refused))
    with pytest.raises(AppError) as err:
        backend.chat("S", [Turn("user", "Q")])
    assert "declined" in err.value.problem and "cyber" in err.value.problem


def test_cut_off_answer_gets_a_note():
    backend, _ = _backend("claude-opus-5-5", (200, _message([{"type": "text", "text": "partial"}], stop_reason="max_tokens")))
    reply = backend.chat("S", [Turn("user", "Q")])
    assert reply.text == "partial" and "max_tokens" in reply.note


def test_bad_key_and_bad_model_errors():
    unauthorized = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    backend, _ = _backend("claude-opus-5-5", (401, unauthorized))
    with pytest.raises(AppError) as err:
        backend.chat("S", [Turn("user", "Q")])
    assert err.value.kind == "auth" and "invalid x-api-key" in err.value.problem

    not_found = {"type": "error", "error": {"type": "not_found_error", "message": "model: claude-nope"}}
    backend, _ = _backend("claude-nope", (404, not_found))
    with pytest.raises(AppError) as err:
        backend.chat("S", [Turn("user", "Q")])
    assert err.value.kind == "model" and "claude-nope" in err.value.problem
