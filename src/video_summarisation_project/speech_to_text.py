"""Audio file -> transcript text, using Groq's Whisper models.

For platforms that don't publish captions (Instagram Reels). It always uses Groq,
whatever the chat vendor is, with the Groq key saved by `/add-api-key groq` (or
$GROQ_API_KEY). The audio file is uploaded to Groq; nothing else is.
"""

from __future__ import annotations

from pathlib import Path

import groq
import httpx

from .config import VENDOR_INFO, Config, api_key_for, config_path
from .errors import AppError
from .vendors import _api_detail

# Groq's upload limit for a single audio file on the free tier.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
# Whisper tends to invent a word or two ("Thank you.", "♪") on music or silence,
# so a transcript shorter than this counts as "no speech".
MIN_WORDS = 5

_KEY_URL = VENDOR_INFO["groq"].key_url


def require_groq_key(config: Config) -> str:
    """The Groq key used for transcription. Checked before anything is downloaded."""
    key, _ = api_key_for(config, "groq")
    if not key:
        raise AppError(
            "Instagram reels are transcribed with Groq, but no Groq API key is saved.",
            f"Run /add-api-key groq to add one (free at {_KEY_URL}). You can keep chatting with your current vendor.",
            kind="config",
        )
    return key


def _http_error(status: int, detail: str, model: str) -> AppError:
    low = detail.lower()
    if status == 401:
        return AppError(
            f"Groq rejected your API key ({detail}).",
            f"ytchat transcribes Instagram reels with Groq. Run /add-api-key groq to save a valid key (create one at {_KEY_URL}).",
            kind="auth",
        )
    if status == 404 or "model_not_found" in low or "does not exist" in low:
        return AppError(
            f"Groq doesn't offer the speech-to-text model '{model}' ({detail}).",
            f"Set transcription_model in {config_path()} to a current Groq Whisper model, e.g. whisper-large-v3-turbo.",
            kind="model",
        )
    if status == 413:
        return AppError(f"This reel's audio is too large for Groq to transcribe ({detail}).", "Try a shorter reel.", kind="limit")
    if status == 429:
        return AppError(
            f"Groq speech-to-text rate limit or quota reached ({detail}).",
            "Wait a minute and try again. If it keeps happening, check your plan's limits in the Groq console.",
            kind="limit",
        )
    if status >= 500:
        return AppError(f"Groq's speech-to-text is having problems right now (HTTP {status}: {detail}).", "Try again in a moment.", kind="network")
    return AppError(f"Groq couldn't transcribe this reel's audio (HTTP {status}: {detail}).", "Try another reel.")


def transcribe(audio: Path, config: Config, *, http_client: httpx.Client | None = None) -> str:
    """The speech in `audio` as plain text. Raises AppError."""
    key = require_groq_key(config)
    size = audio.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise AppError(
            f"This reel's audio is too large to transcribe ({size / 1024 / 1024:.0f} MB; Groq accepts up to "
            f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB).",
            "Try a shorter reel.",
            kind="limit",
        )

    model = config.transcription_model
    client = groq.Groq(api_key=key, http_client=http_client)
    try:
        # Read the bytes up front so no file handle stays open (Windows can't delete open files).
        result = client.audio.transcriptions.create(file=(audio.name, audio.read_bytes()), model=model, temperature=0)
    except groq.APIStatusError as exc:
        raise _http_error(exc.status_code, _api_detail(exc), model) from exc
    except groq.APIConnectionError as exc:  # includes timeouts
        what = "the request timed out" if isinstance(exc, groq.APITimeoutError) else "network error"
        raise AppError(
            f"Couldn't reach Groq to transcribe the reel ({what}).",
            "Check your internet connection (and any proxy or VPN), then try again.",
            kind="network",
        ) from exc

    text = " ".join(result.text.split())
    if len(text.split()) < MIN_WORDS:
        heard = f' (all it heard was "{text}")' if text else ""
        raise AppError(
            f"There's too little speech in this reel to chat about{heard}.",
            "ytchat works from what's said in a reel, so music-only reels and on-screen text can't be summarised. Try another reel.",
            kind="input",
        )
    return text
