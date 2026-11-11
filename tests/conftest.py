import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Every test gets its own empty settings folder and no API keys from the environment."""
    monkeypatch.setenv("YTCHAT_CONFIG_DIR", str(tmp_path / "ytchat"))
    for var in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path / "ytchat"
