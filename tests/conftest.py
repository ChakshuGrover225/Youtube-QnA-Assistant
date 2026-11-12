import pytest

from video_summarisation_project import transcript_files


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Every test gets its own empty settings folder and no API keys from the environment."""
    monkeypatch.setenv("YTCHAT_CONFIG_DIR", str(tmp_path / "ytchat"))
    for var in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    # The default /save-transcript folder is next to the code: point it at the temp folder too.
    monkeypatch.setattr(transcript_files, "_PACKAGE_DIR", tmp_path / "package")
    return tmp_path / "ytchat"
