"""Where ytchat keeps its settings, and how they are loaded and saved.

Settings live in one JSON file in your user config folder, so the tool works
the same from any directory:

    Windows:      %APPDATA%\\ytchat\\config.json
    macOS/Linux:  ~/.config/ytchat/config.json   ($XDG_CONFIG_HOME is respected)

Set YTCHAT_CONFIG_DIR to keep it somewhere else. API keys are stored in this
file in plain text (like most CLI tools), readable only by your user account.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, Field, ValidationError

from .errors import AppError

Vendor = Literal["anthropic", "groq", "ollama"]
VENDORS: tuple[Vendor, ...] = get_args(Vendor)

CONFIG_DIR_ENV = "YTCHAT_CONFIG_DIR"


@dataclass(frozen=True)
class VendorInfo:
    label: str
    default_model: str
    needs_key: bool
    env_var: str | None = None  # used when no key has been saved with /add-api-key
    key_prefix: str | None = None  # what this vendor's API keys start with
    key_url: str | None = None
    models_url: str | None = None

    @property
    def a_label(self) -> str:
        """'an Anthropic', 'a Groq', 'an Ollama'."""
        return ("an " if self.label[0] in "AEIOU" else "a ") + self.label


VENDOR_INFO: dict[Vendor, VendorInfo] = {
    "anthropic": VendorInfo(
        label="Anthropic",
        default_model="claude-opus-5-5",
        needs_key=True,
        env_var="ANTHROPIC_API_KEY",
        key_prefix="sk-ant-",
        key_url="https://platform.claude.com/settings/keys",
        models_url="https://platform.claude.com/docs/en/about-claude/models/overview",
    ),
    "groq": VendorInfo(
        label="Groq",
        default_model="openai/gpt-oss-120b",
        needs_key=True,
        env_var="GROQ_API_KEY",
        key_prefix="gsk_",
        key_url="https://console.groq.com/keys",
        models_url="https://console.groq.com/docs/models",
    ),
    "ollama": VendorInfo(
        label="Ollama",
        default_model="qwen3:0.6b",
        needs_key=False,
        models_url="https://ollama.com/library",
    ),
}


class VendorSettings(BaseModel):
    model: str = Field(min_length=1)
    api_key: str | None = None
    # Ollama only. None = $OLLAMA_HOST, or http://localhost:11434 if that's unset.
    host: str | None = None


def _vendor_defaults(vendor: Vendor) -> VendorSettings:
    return VendorSettings(model=VENDOR_INFO[vendor].default_model)


class VendorTable(BaseModel):
    """Each vendor remembers its own model and key, so switching back and forth is painless."""

    anthropic: VendorSettings = Field(default_factory=lambda: _vendor_defaults("anthropic"))
    groq: VendorSettings = Field(default_factory=lambda: _vendor_defaults("groq"))
    ollama: VendorSettings = Field(default_factory=lambda: _vendor_defaults("ollama"))


class Config(BaseModel):
    # The vendor in use: /change-vendor.
    vendor: Vendor = "groq"
    vendors: VendorTable = Field(default_factory=VendorTable)

    # Advanced settings - edit the config file to change them.
    # 0 = focused and consistent, higher = more varied. Used by Groq and Ollama;
    # current Claude models don't accept it, so Anthropic requests leave it out.
    temperature: float = Field(default=0.3, ge=0, le=2)
    # Maximum length of each answer in tokens. None = the vendor's default.
    max_tokens: int | None = Field(default=None, gt=0)
    # Extra instructions added to the system prompt, e.g. "Keep answers under 100 words."
    additional_prompt: str = ""
    # Preferred transcript languages, in priority order. If none exist, any is used.
    transcript_languages: list[str] = Field(default_factory=lambda: ["en"])

    def settings_for(self, vendor: Vendor | None = None) -> VendorSettings:
        return getattr(self.vendors, vendor or self.vendor)


def config_dir() -> Path:
    if override := os.environ.get(CONFIG_DIR_ENV, "").strip():
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ytchat"


def config_path() -> Path:
    return config_dir() / "config.json"


_RESET_HINT = (
    "Fix it in a text editor, or delete the file to start over with default settings "
    "(you'll need to add your API keys again)."
)


def load_config(path: Path | None = None) -> Config:
    """Load settings, or return the defaults if nothing has been saved yet."""
    path = path or config_path()
    if not path.exists():
        return Config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(f"Couldn't read your settings file {path} ({exc}).", _RESET_HINT, kind="config") from exc
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']) or 'file'}: {err['msg']}" for err in exc.errors()
        )
        raise AppError(f"Your settings file {path} has invalid values - {details}.", _RESET_HINT, kind="config") from exc


def save_config(config: Config, path: Path | None = None) -> Path:
    """Write settings atomically, so a crash never leaves a half-written file."""
    path = path or config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
        if os.name != "nt":
            os.chmod(tmp, 0o600)  # the file holds API keys
        os.replace(tmp, path)
    except OSError as exc:
        raise AppError(
            f"Couldn't save your settings to {path} ({exc}).",
            f"Check that the folder is writable, or set {CONFIG_DIR_ENV} to a folder that is.",
            kind="config",
        ) from exc
    return path


def api_key_for(config: Config, vendor: Vendor) -> tuple[str | None, str]:
    """Return (key, where it came from). A key saved with /add-api-key wins over the env var."""
    info = VENDOR_INFO[vendor]
    if saved := config.settings_for(vendor).api_key:
        return saved, "saved"
    if info.env_var and (from_env := os.environ.get(info.env_var, "").strip()):
        return from_env, f"${info.env_var}"
    return None, "missing"


def vendor_for_key(key: str) -> Vendor | None:
    """Guess which vendor issued a key from its prefix (sk-ant-..., gsk_...)."""
    for vendor, info in VENDOR_INFO.items():
        if info.key_prefix and key.startswith(info.key_prefix):
            return vendor
    return None


def mask_key(key: str) -> str:
    return f"{key[:4]}…{key[-4:]}" if len(key) > 12 else "…" * 3
