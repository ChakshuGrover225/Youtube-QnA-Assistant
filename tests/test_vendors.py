import pytest

from video_summarisation_project.config import Config
from video_summarisation_project.errors import AppError
from video_summarisation_project.vendors import (
    GroqBackend,
    ModelInfo,
    OllamaBackend,
    guess_vendor,
    http_error,
    make_backend,
    normalize_model_name,
    resolve_model,
    _strip_thinking,
)


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("opus 5.5", "claude-opus-5-5"),
        ("Opus 5.5", "claude-opus-5-5"),
        ("Claude Sonnet 5.5", "claude-sonnet-5-5"),
        ("haiku-5-5", "claude-haiku-5-5"),
        ("fable 5.2", "claude-fable-5-2"),
        ("opus 5", "claude-opus-5"),
        ("claude-opus-5-5", "claude-opus-5-5"),
        ("CLAUDE-HAIKU-4-5", "claude-haiku-4-5"),
    ],
)
def test_friendly_claude_names(typed, expected):
    assert normalize_model_name("anthropic", typed) == expected


def test_other_vendors_keep_names_as_typed():
    assert normalize_model_name("ollama", " qwen3:0.6B ") == "qwen3:0.6B"
    assert normalize_model_name("groq", "openai/gpt-oss-120b") == "openai/gpt-oss-120b"


def test_guess_vendor():
    assert guess_vendor("opus 5.5") == "anthropic"
    assert guess_vendor("claude-sonnet-5-5") == "anthropic"
    assert guess_vendor("qwen3:0.6B") == "ollama"
    assert guess_vendor("openai/gpt-oss-120b") is None


def test_resolve_model_shorthands():
    ollama_models = [ModelInfo("qwen3:0.6b"), ModelInfo("llama3.2:latest")]
    assert resolve_model("ollama", "qwen3:0.6B", ollama_models) == "qwen3:0.6b"
    assert resolve_model("ollama", "llama3.2", ollama_models) == "llama3.2:latest"

    groq_models = [ModelInfo("openai/gpt-oss-120b"), ModelInfo("openai/gpt-oss-20b")]
    assert resolve_model("groq", "gpt-oss-20b", groq_models) == "openai/gpt-oss-20b"

    claude_models = [ModelInfo("claude-opus-5-5", "Claude Opus 5.5"), ModelInfo("claude-haiku-5-5", "Claude Haiku 5.5")]
    assert resolve_model("anthropic", "opus 5.5", claude_models) == "claude-opus-5-5"
    assert resolve_model("anthropic", "Claude Haiku 5.5", claude_models) == "claude-haiku-5-5"


def test_unknown_model_suggests_close_matches():
    with pytest.raises(AppError) as err:
        resolve_model("groq", "gpt-oss-12b", [ModelInfo("openai/gpt-oss-120b"), ModelInfo("whisper-large-v3")])
    assert err.value.kind == "model"
    assert "Did you mean: openai/gpt-oss-120b?" in err.value.fix


def test_model_from_another_vendor_gets_a_vendor_hint():
    with pytest.raises(AppError) as err:
        resolve_model("groq", "opus 5.5", [ModelInfo("openai/gpt-oss-120b")])
    assert "/change-vendor anthropic" in err.value.fix


def test_missing_ollama_model_suggests_pull():
    with pytest.raises(AppError) as err:
        resolve_model("ollama", "llama3.2", [ModelInfo("qwen3:0.6b")])
    assert "isn't installed in Ollama" in err.value.problem
    assert "ollama pull llama3.2" in err.value.fix


@pytest.mark.parametrize(
    ("status", "detail", "kind", "phrase"),
    [
        (401, "Invalid API Key", "auth", "/add-api-key"),
        (404, "The model `x` does not exist", "model", "/models"),
        (413, "Request too large for model on tokens per minute (TPM)", "limit", "shorter video"),
        (400, "prompt is too long: 250000 tokens > 200000 maximum", "limit", "bigger limits"),
        (429, "Rate limit reached", "limit", "Wait a minute"),
        (400, "The model `x` has been decommissioned", "model", "/change-model"),
        (503, "Service unavailable", "network", "Try again"),
    ],
)
def test_http_errors_become_actionable(status, detail, kind, phrase):
    err = http_error("groq", "x", "gsk_abc", status, detail)
    assert err.kind == kind
    assert detail in err.problem
    assert phrase in err.fix


def test_401_points_out_a_key_from_the_wrong_vendor():
    err = http_error("groq", "m", "sk-ant-api03-abc", 401, "Invalid API Key")
    assert "looks like an Anthropic key" in err.fix


def test_missing_key_is_reported_before_any_request():
    with pytest.raises(AppError) as err:
        make_backend(Config(), "anthropic")
    assert err.value.kind == "config"
    assert "No API key saved for Anthropic" in err.value.problem
    assert "/add-api-key" in err.value.fix
    assert "ANTHROPIC_API_KEY" in err.value.fix


def test_unknown_vendor_is_rejected():
    with pytest.raises(AppError) as err:
        make_backend(Config(), "openai")  # type: ignore[arg-type]
    assert "Unknown vendor" in err.value.problem


def test_make_backend_uses_env_key_and_ollama_needs_none(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_env")
    groq_backend = make_backend(Config(), "groq")
    assert isinstance(groq_backend, GroqBackend) and groq_backend.api_key == "gsk_env"
    assert isinstance(make_backend(Config(), "ollama"), OllamaBackend)


def test_ollama_context_window_fits_the_transcript():
    backend = OllamaBackend("qwen3:0.6b", Config())
    short = backend._context_size([{"role": "system", "content": "x" * 400}])
    assert short == OllamaBackend.MIN_CONTEXT

    long_transcript = [{"role": "system", "content": "x" * 200_000}]  # ~50k tokens
    assert backend._context_size(long_transcript) > 50_000

    backend.context_limit = 32_768
    with pytest.raises(AppError) as err:
        backend._context_size(long_transcript)
    assert err.value.kind == "limit"


def test_think_tags_are_removed():
    assert _strip_thinking("<think>hmm</think>\n\nAnswer") == "Answer"
    assert _strip_thinking("<think>never closed") == ""
    assert _strip_thinking("Plain answer") == "Plain answer"
