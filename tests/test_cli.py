"""The interactive app, driven with scripted input and a fake LLM backend."""

import io

import pytest
from rich.console import Console

from video_summarisation_project import cli, vendors
from video_summarisation_project.config import Config, load_config
from video_summarisation_project.errors import AppError
from video_summarisation_project.vendors import Backend, ModelInfo, Reply


class FakeBackend(Backend):
    """Stands in for a vendor. `fail` makes every call raise that AppError."""

    vendor = "groq"
    models = {
        "groq": [ModelInfo("openai/gpt-oss-120b"), ModelInfo("openai/gpt-oss-20b")],
        "anthropic": [ModelInfo("claude-opus-5-5", "Claude Opus 5.5"), ModelInfo("claude-sonnet-5-5", "Claude Sonnet 5.5")],
        "ollama": [ModelInfo("qwen3:0.6b")],
    }
    fail: AppError | None = None
    fail_chat: AppError | None = None

    def list_models(self):
        if FakeBackend.fail:
            raise FakeBackend.fail
        return self.models[self.vendor]

    def chat(self, system, turns):
        if FakeBackend.fail_chat:
            raise FakeBackend.fail_chat
        assert "## Transcript\nthe transcript" in system
        return Reply(f"answer {len(turns)}: {turns[-1].text}")


@pytest.fixture
def fake_vendor(monkeypatch):
    FakeBackend.fail = FakeBackend.fail_chat = None

    def fake_make_backend(config, vendor=None, *, model=None, api_key=None):
        vendor = vendor or config.vendor
        backend = FakeBackend(model or config.settings_for(vendor).model, config, api_key)
        backend.vendor = vendor
        return backend

    monkeypatch.setattr(vendors, "make_backend", fake_make_backend)
    monkeypatch.setattr(cli, "fetch_transcript", lambda video_id, languages: "the transcript")
    return FakeBackend


def run(*lines, config=None):
    """Run the app with `lines` as typed input; return (output, saved config)."""
    output = io.StringIO()
    console = Console(file=output, width=120, color_system=None)
    queue = list(lines)

    def fake_input(prompt="", password=False):
        console.print(prompt)  # what was typed is not echoed, so secrets never reach the output
        if not queue:
            raise EOFError
        return queue.pop(0)

    console.input = fake_input
    exit_code = cli.App(console, config or Config()).run()
    assert exit_code == 0
    return output.getvalue(), load_config()


def test_full_conversation_ends_with_exit(fake_vendor):
    out, _ = run("https://youtu.be/jNQXAC9IVRw", "What is it about?", "And then?", "/exit", "never read")
    assert "Video summary" in out
    assert "answer 1: Summarise this video." in out  # summary request is the first turn
    assert "answer 3: What is it about?" in out
    assert "answer 5: And then?" in out  # follow-ups keep the whole history
    assert "Conversation ended" in out
    assert "never read" not in out


def test_change_vendor_is_saved(fake_vendor):
    out, saved = run("/change-vendor ollama", "/exit")
    assert saved.vendor == "ollama"
    assert "Vendor set to Ollama" in out and "Ready: Ollama" in out


def test_change_vendor_by_number_and_prompt(fake_vendor):
    _, saved = run("/change-vendor", "1", "", "/exit")  # 1 = anthropic, then skip the key prompt
    assert saved.vendor == "anthropic"


def test_unsupported_vendor_is_rejected_and_not_saved(fake_vendor):
    out, saved = run("/change-vendor openai", "/exit")
    assert "'openai' isn't a supported vendor" in out
    assert "anthropic, groq, ollama" in out
    assert saved.vendor == "groq"


def test_change_vendor_asks_for_missing_key(fake_vendor):
    out, saved = run("/change-vendor anthropic", "sk-ant-api03-good-key-123", "/exit")
    assert saved.vendor == "anthropic"
    assert saved.settings_for("anthropic").api_key == "sk-ant-api03-good-key-123"
    assert "verified and saved" in out


def test_add_api_key_is_saved(fake_vendor):
    out, saved = run("/add-api-key", "gsk_valid_key_1234567890", "/exit")
    assert saved.settings_for("groq").api_key == "gsk_valid_key_1234567890"
    assert "gsk_valid_key_1234567890" not in out  # only the masked form is printed


def test_add_api_key_for_named_vendor(fake_vendor):
    _, saved = run("/add-api-key anthropic", "sk-ant-api03-abc-1234567", "/exit")
    assert saved.vendor == "groq"
    assert saved.settings_for("anthropic").api_key == "sk-ant-api03-abc-1234567"


def test_rejected_key_is_not_saved(fake_vendor):
    fake_vendor.fail = AppError("Groq rejected your API key (Invalid API Key).", "Run /add-api-key ...", kind="auth")
    out, saved = run("/add-api-key gsk_wrong_key_1234567890", "/exit")
    assert "API key problem" in out and "Key not saved" in out
    assert saved.settings_for("groq").api_key is None


def test_key_from_the_wrong_vendor_is_not_saved(fake_vendor):
    out, saved = run("/add-api-key sk-ant-api03-abc-1234567", "/exit")
    assert "looks like an Anthropic key, not a Groq key" in out
    assert saved.settings_for("groq").api_key is None


def test_unverifiable_key_is_saved_with_a_warning(fake_vendor):
    fake_vendor.fail = AppError("Couldn't reach Groq (network error).", kind="network")
    out, saved = run("/add-api-key gsk_offline_key_1234567", "/exit")
    assert saved.settings_for("groq").api_key == "gsk_offline_key_1234567"
    assert "Couldn't verify" in out and "saved (not verified)" in out


def test_ollama_needs_no_key(fake_vendor):
    out, _ = run("/add-api-key ollama", "/exit")
    assert "doesn't need an API key" in out


def test_change_model_is_saved_with_exact_name(fake_vendor):
    out, saved = run("/change-model gpt-oss-20b", "/exit")
    assert saved.settings_for("groq").model == "openai/gpt-oss-20b"
    assert "Model set to openai/gpt-oss-20b" in out


def test_unknown_model_is_not_saved(fake_vendor):
    out, saved = run("/change-model gpt-oss-12b", "/exit")
    assert "Model problem" in out and "Did you mean" in out and "Model not changed" in out
    assert saved.settings_for("groq").model == "openai/gpt-oss-120b"


def test_model_for_another_vendor_is_caught_even_offline(fake_vendor):
    fake_vendor.fail = AppError("No API key saved for Groq.", "Run /add-api-key", kind="config")
    out, saved = run("/change-model opus 5.5", "/exit")
    assert "looks like an Anthropic model" in out and "/change-vendor anthropic" in out
    assert saved.settings_for("groq").model == "openai/gpt-oss-120b"


def test_friendly_claude_name_is_saved_when_vendor_unreachable(fake_vendor):
    fake_vendor.fail = AppError("No API key saved for Anthropic.", "Run /add-api-key", kind="config")
    config = Config(vendor="anthropic")
    out, saved = run("/change-model sonnet 5.5", "/exit", config=config)
    assert saved.settings_for("anthropic").model == "claude-sonnet-5-5"
    assert "not verified yet" in out


def test_setup_problem_stops_before_fetching_transcript(fake_vendor, monkeypatch):
    fake_vendor.fail = AppError("No API key saved for Groq.", "Run /add-api-key", kind="config")
    monkeypatch.setattr(cli, "fetch_transcript", lambda *a: pytest.fail("should not fetch"))
    out, _ = run("https://youtu.be/jNQXAC9IVRw", "/exit")
    assert "Setup problem" in out and "No API key saved for Groq" in out


def test_failed_question_keeps_the_conversation_going(fake_vendor):
    output, _ = run("https://youtu.be/jNQXAC9IVRw", "/exit")  # sanity: summary works
    assert "Video summary" in output

    app_out = io.StringIO()
    console = Console(file=app_out, width=120, color_system=None)
    lines = ["https://youtu.be/jNQXAC9IVRw", "Q1", "Q2", "/exit"]

    def fake_input(prompt="", password=False):
        line = lines.pop(0)
        # Q1 fails with a rate limit; Q2 succeeds and must not see Q1 in the history.
        fake_vendor.fail_chat = AppError("Groq rate limit reached.", "Wait a minute", kind="limit") if line == "Q1" else None
        return line

    console.input = fake_input
    app = cli.App(console, Config())
    app.run()
    out = app_out.getvalue()
    assert "Limit reached" in out
    assert "answer 3: Q2" in out  # summary (2 turns) + Q2; the failed Q1 was dropped


def test_new_and_unknown_commands(fake_vendor):
    out, _ = run("/new", "https://youtu.be/jNQXAC9IVRw", "/new", "/nope", "/exit")
    assert "No video is open" in out
    assert "Closed the video" in out
    assert "Unknown command '/nope'" in out


def test_byte_order_mark_from_powershell_pipes_is_ignored(fake_vendor):
    out, saved = run("﻿/change-vendor ollama", "/exit")
    assert saved.vendor == "ollama"


def test_invalid_link(fake_vendor):
    out, _ = run("not a link", "/exit")
    assert "That's not a YouTube video link" in out
