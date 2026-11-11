"""Settings for the YouTube summarisation pipeline.

Edit the defaults below to change how the pipeline behaves. Any setting can
also be overridden by an environment variable or a line in the project's .env
file with the same name (e.g. TEMPERATURE=0.7). Secrets like the Groq API key
belong in .env, never in this file.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LOGIC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = LOGIC_DIR.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Groq ---------------------------------------------------------------

    # API key from https://console.groq.com/keys. Set GROQ_API_KEY in .env.
    groq_api_key: SecretStr | None = None

    # Model to use (see https://console.groq.com/docs/models).
    model: str = "openai/gpt-oss-120b"

    # 0 = focused and consistent, higher = more varied. Groq accepts 0-2.
    temperature: float = Field(default=0.3, ge=0, le=2)

    # Maximum length of each response, in tokens. None = the model's default.
    # Reasoning models count their thinking towards this, so don't set it too low.
    max_tokens: int | None = Field(default=None, gt=0)

    # How much reasoning models (e.g. openai/gpt-oss-*) think before answering.
    # Leave as None for models that don't support it, like Llama.
    reasoning_effort: Literal["low", "medium", "high"] | None = None

    # --- Prompts ------------------------------------------------------------

    # Folder holding the prompt files.
    prompt_dir: Path = LOGIC_DIR / "prompt_library"

    # Instructions for the opening summary.
    summary_prompt_file: str = "system_prompt.md"

    # Instructions for answering questions in the conversation. The transcript
    # is appended automatically.
    chat_prompt_file: str = "chat_system_prompt.md"

    # Extra instructions added to both prompts, e.g. "Focus on the technical
    # details." or "Keep every answer under 100 words." Empty = none.
    additional_prompt: str = ""

    # --- Transcript & conversation -----------------------------------------

    # Preferred transcript languages, in priority order. If none of these exist,
    # whichever transcript the video has is used.
    transcript_languages: list[str] = ["en"]

    # Typing this during the conversation ends it.
    exit_command: str = "/exit"


settings = Settings()
