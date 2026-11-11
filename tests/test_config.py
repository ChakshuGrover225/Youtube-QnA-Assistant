import json

import pytest

from video_summarisation_project.config import (
    Config,
    api_key_for,
    config_path,
    load_config,
    mask_key,
    save_config,
    vendor_for_key,
)
from video_summarisation_project.errors import AppError


def test_defaults_when_nothing_saved():
    config = load_config()
    assert config.vendor == "groq"
    assert config.settings_for().model == "openai/gpt-oss-120b"
    assert config.settings_for("anthropic").model == "claude-opus-5-5"
    assert config.settings_for("ollama").model == "qwen3:0.6b"


def test_config_dir_override(isolated_config):
    assert config_path() == isolated_config / "config.json"


def test_vendor_model_and_key_survive_a_restart():
    config = Config()
    config.vendor = "anthropic"
    config.settings_for("anthropic").model = "claude-sonnet-5-5"
    config.settings_for("anthropic").api_key = "sk-ant-secret-1234567890"
    path = save_config(config)

    reloaded = load_config(path)
    assert reloaded.vendor == "anthropic"
    assert reloaded.settings_for().model == "claude-sonnet-5-5"
    assert reloaded.settings_for().api_key == "sk-ant-secret-1234567890"
    assert not path.with_name("config.json.tmp").exists()


def test_broken_json_is_a_config_error_not_a_crash():
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(AppError) as err:
        load_config()
    assert err.value.kind == "config"
    assert str(path) in err.value.problem
    assert "delete the file" in err.value.fix


def test_unknown_vendor_in_file_is_reported():
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"vendor": "openai"}), encoding="utf-8")
    with pytest.raises(AppError) as err:
        load_config()
    assert "vendor" in err.value.problem
    assert "'anthropic', 'groq' or 'ollama'" in err.value.problem


def test_saved_key_wins_over_environment(monkeypatch):
    config = Config()
    assert api_key_for(config, "groq") == (None, "missing")

    monkeypatch.setenv("GROQ_API_KEY", "gsk_from_env")
    assert api_key_for(config, "groq") == ("gsk_from_env", "$GROQ_API_KEY")

    config.settings_for("groq").api_key = "gsk_saved"
    assert api_key_for(config, "groq") == ("gsk_saved", "saved")


def test_key_prefix_detection_and_masking():
    assert vendor_for_key("sk-ant-api03-abc") == "anthropic"
    assert vendor_for_key("gsk_abc") == "groq"
    assert vendor_for_key("something-else") is None
    assert mask_key("gsk_1234567890abcdef") == "gsk_…cdef"
    assert "1234" not in mask_key("short1234")
