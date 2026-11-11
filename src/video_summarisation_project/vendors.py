"""The three LLM vendors behind one small interface.

Each vendor is called through its own official SDK (anthropic, groq, ollama).
Every SDK error is turned into an AppError that says what went wrong and how
to fix it, so a wrong vendor / model / key combination never ends in a traceback.
"""

from __future__ import annotations

import difflib
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Literal

import anthropic
import groq
import httpx
import ollama

from .config import VENDOR_INFO, VENDORS, Config, Vendor, api_key_for, vendor_for_key
from .errors import AppError


@dataclass
class Turn:
    """One message in the conversation, kept in a vendor-neutral form."""

    role: Literal["user", "assistant"]
    text: str
    # The vendor's own response content, replayed unchanged when the same vendor
    # answers the next question (Anthropic needs its thinking blocks sent back).
    raw: Any = None
    raw_vendor: Vendor | None = None


@dataclass
class Reply:
    text: str
    raw: Any = None
    note: str | None = None  # shown under the answer, e.g. when it was cut off


@dataclass
class ModelInfo:
    id: str
    note: str = ""  # display name, context size, download size...


# --- Model names -------------------------------------------------------------

# "opus 5.5", "Claude Sonnet 4.6", "haiku-5-5", "fable 5.2" ...
_CLAUDE_NAME = re.compile(
    r"^(?:claude[\s_-]*)?(opus|sonnet|haiku|fable|mythos)[\s_-]*(\d+)(?:[.\s_-]+(\d+))?$", re.IGNORECASE
)


def normalize_model_name(vendor: Vendor, name: str) -> str:
    """Turn friendly names into model IDs where we can, e.g. "opus 5.5" -> "claude-opus-5-5"."""
    name = " ".join(name.split())
    if vendor == "anthropic":
        if match := _CLAUDE_NAME.match(name):
            family, major, minor = match.groups()
            return f"claude-{family.lower()}-{major}" + (f"-{minor}" if minor else "")
        return name.lower()  # Claude model IDs are always lowercase
    return name


def guess_vendor(name: str) -> Vendor | None:
    """Best guess at which vendor a model name belongs to, for "wrong vendor?" hints."""
    name = name.strip()
    if _CLAUDE_NAME.match(name) or name.lower().startswith("claude"):
        return "anthropic"
    if ":" in name:  # Ollama tags look like name:tag
        return "ollama"
    return None


def resolve_model(vendor: Vendor, requested: str, models: list[ModelInfo]) -> str:
    """Return the exact ID of `requested` among `models`, or raise a helpful AppError.

    Matching is case-insensitive and accepts a few shorthands: Claude display
    names ("Claude Opus 5.5"), Groq IDs without the org ("gpt-oss-120b"), and
    Ollama names without ":latest".
    """
    lookup: dict[str, str] = {}
    for m in models:
        lookup.setdefault(m.id.lower(), m.id)
    for m in models:
        if vendor == "anthropic" and m.note:
            lookup.setdefault(m.note.lower(), m.id)
            lookup.setdefault(m.note.lower().removeprefix("claude "), m.id)
        elif vendor == "groq" and "/" in m.id:
            lookup.setdefault(m.id.split("/", 1)[1].lower(), m.id)
        elif vendor == "ollama" and m.id.endswith(":latest"):
            lookup.setdefault(m.id.removesuffix(":latest").lower(), m.id)

    for candidate in (normalize_model_name(vendor, requested), requested.strip()):
        if found := lookup.get(candidate.lower()):
            return found
    raise model_not_found(vendor, requested, [m.id for m in models])


def model_not_found(
    vendor: Vendor, model: str, available: list[str] | None = None, detail: str | None = None
) -> AppError:
    info = VENDOR_INFO[vendor]
    where = "installed in Ollama" if vendor == "ollama" else f"available on {info.label}"
    problem = f"Model '{model}' isn't {where}" + (f" ({detail})" if detail else "") + "."

    fixes: list[str] = []
    guessed = guess_vendor(model)
    wrong_vendor = guessed is not None and guessed != vendor
    if wrong_vendor:
        fixes.append(
            f"'{model}' looks like {VENDOR_INFO[guessed].a_label} model - switch with /change-vendor {guessed}."
        )
    if available:
        by_lower = {a.lower(): a for a in available}
        close = difflib.get_close_matches(model.lower(), list(by_lower), n=3, cutoff=0.5)
        if close:
            fixes.append("Did you mean: " + ", ".join(by_lower[c] for c in close) + "?")
    if vendor == "ollama" and not wrong_vendor:
        fixes.append(f"Download it with `ollama pull {model}`, or pick an installed one: /models, then /change-model <name>.")
    else:
        fixes.append("Run /models to see what's available, then /change-model <name>.")
    return AppError(problem, " ".join(fixes), kind="model")


# --- Error translation for the Anthropic and Groq SDKs ------------------------


def _api_detail(exc: Exception) -> str:
    """The vendor's own error message, without the SDK's wrapping."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return error
    return str(getattr(exc, "message", "") or exc)


def http_error(vendor: Vendor, model: str, key: str | None, status: int, detail: str) -> AppError:
    """Map an HTTP error from a vendor API to a problem + fix the user can act on."""
    info = VENDOR_INFO[vendor]
    label = info.label
    low = detail.lower()

    if status == 401:
        fix = f"Run /add-api-key to save a valid {label} key" + (f" (create one at {info.key_url})." if info.key_url else ".")
        owner = vendor_for_key(key) if key else None
        if owner and owner != vendor:
            fix += f" The key in use looks like {VENDOR_INFO[owner].a_label} key."
        elif key and info.key_prefix and not key.startswith(info.key_prefix):
            fix += f" {label} keys start with '{info.key_prefix}'."
        return AppError(f"{label} rejected your API key ({detail}).", fix, kind="auth")
    if status == 404 or "model_not_found" in low:
        return model_not_found(vendor, model, detail=detail)
    if status == 413 or (
        status == 400 and any(s in low for s in ("context length", "context_length", "context window", "too long", "too large"))
    ):
        return AppError(
            f"This conversation is too long for '{model}' on {label} ({detail}).",
            "Long videos can exceed a model's context window or your plan's tokens-per-minute limit. "
            "Pick a model with bigger limits (/models, /change-model), try a shorter video, or switch vendor (/change-vendor).",
            kind="limit",
        )
    if status == 429:
        return AppError(
            f"{label} rate limit or quota reached ({detail}).",
            "Wait a minute and try again, or switch model (/change-model) or vendor (/change-vendor). "
            "If it keeps happening, check your plan's limits.",
            kind="limit",
        )
    if "decommissioned" in low or "deprecated" in low or "retired" in low:
        return AppError(f"'{model}' has been retired by {label} ({detail}).", "Pick a current model: /models, then /change-model <name>.", kind="model")
    if "credit balance" in low or "billing" in low:
        return AppError(f"{label} can't bill this request ({detail}).", f"Add credits or check billing in your {label} console, then try again.", kind="limit")
    if status == 403:
        return AppError(
            f"{label} denied access ({detail}).",
            f"Your key may not have access to '{model}', or your account or region is restricted. "
            f"Try another model (/models) or check your {label} console.",
        )
    if status >= 500:
        return AppError(f"{label} is having problems right now (HTTP {status}: {detail}).", "Try again in a moment, or switch vendor with /change-vendor.", kind="network")
    return AppError(f"{label} rejected the request (HTTP {status}: {detail}).", "Check the model with /models. If it looks right, try again.")


@contextmanager
def _sdk_errors(sdk: ModuleType, vendor: Vendor, model: str, key: str | None) -> Iterator[None]:
    """Translate errors from the anthropic / groq SDKs (both share the same error classes)."""
    try:
        yield
    except sdk.APIStatusError as exc:
        raise http_error(vendor, model, key, exc.status_code, _api_detail(exc)) from exc
    except sdk.APIConnectionError as exc:  # includes timeouts
        what = "the request timed out" if isinstance(exc, sdk.APITimeoutError) else "network error"
        raise AppError(
            f"Couldn't reach {VENDOR_INFO[vendor].label} ({what}).",
            "Check your internet connection (and any proxy or VPN), then try again.",
            kind="network",
        ) from exc


_THINK_TAGS = re.compile(r"<think>.*?(?:</think>|\Z)", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Some open models (e.g. Qwen3) put their reasoning in <think> tags inside the answer."""
    return _THINK_TAGS.sub("", text).strip()


_CUT_OFF = "The answer was cut off at the max_tokens limit."


# --- Backends -----------------------------------------------------------------


class Backend(ABC):
    vendor: Vendor

    def __init__(self, model: str, config: Config, api_key: str | None = None) -> None:
        self.model = model
        self.config = config
        self.api_key = api_key

    @property
    def label(self) -> str:
        return VENDOR_INFO[self.vendor].label

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """Models this vendor offers. Also proves the credentials / connection work."""

    def check(self) -> None:
        """Confirm the credentials work and the model exists (fixing its exact spelling)."""
        self.model = resolve_model(self.vendor, self.model, self.list_models())

    @abstractmethod
    def chat(self, system: str, turns: list[Turn]) -> Reply:
        """Answer the last user turn, given the system prompt and the history."""


class AnthropicBackend(Backend):
    vendor = "anthropic"

    # Models that support server-side refusal fallbacks: if a safety classifier
    # declines a request, the API re-runs it on a suitable fallback model.
    FALLBACK_MODELS = frozenset({"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})
    FALLBACK_BETA = "server-side-fallback-2026-07-01"
    # Thinking counts towards max_tokens on current models, so leave plenty of room.
    DEFAULT_MAX_TOKENS = 16_000

    def __init__(self, model: str, config: Config, api_key: str, http_client: Any = None) -> None:
        super().__init__(model, config, api_key)
        self.client = anthropic.Anthropic(api_key=api_key, http_client=http_client)

    def _errors(self):
        return _sdk_errors(anthropic, self.vendor, self.model, self.api_key)

    def list_models(self) -> list[ModelInfo]:
        with self._errors():
            return [ModelInfo(m.id, m.display_name) for m in self.client.models.list(limit=100)]

    def chat(self, system: str, turns: list[Turn]) -> Reply:
        messages = [
            {"role": "assistant", "content": t.raw}
            if t.role == "assistant" and t.raw_vendor == "anthropic" and t.raw is not None
            else {"role": t.role, "content": t.text}
            for t in turns
        ]
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.config.max_tokens or self.DEFAULT_MAX_TOKENS,
            "system": system,
            "messages": messages,
            # The transcript sits in the system prompt and is resent with every
            # question, so caching it makes follow-ups much cheaper and faster.
            "cache_control": {"type": "ephemeral"},
        }
        if self.model in self.FALLBACK_MODELS:
            params["betas"] = [self.FALLBACK_BETA]
            params["fallbacks"] = "default"

        with self._errors():
            response = self.client.beta.messages.create(**params)

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise AppError(
                "Claude declined to answer" + (f" ({category})." if category else "."),
                "Try rephrasing the question, or pick another model with /change-model.",
            )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        note = _CUT_OFF if response.stop_reason == "max_tokens" else None
        return Reply(text, raw=response.content, note=note)


class GroqBackend(Backend):
    vendor = "groq"

    def __init__(self, model: str, config: Config, api_key: str) -> None:
        super().__init__(model, config, api_key)
        self.client = groq.Groq(api_key=api_key)

    def _errors(self):
        return _sdk_errors(groq, self.vendor, self.model, self.api_key)

    def list_models(self) -> list[ModelInfo]:
        with self._errors():
            page = self.client.models.list()
        return [
            ModelInfo(m.id, f"{m.context_window:,}-token context" if getattr(m, "context_window", None) else "")
            for m in page.data
        ]

    def chat(self, system: str, turns: list[Turn]) -> Reply:
        extra: dict[str, Any] = {}
        if self.config.max_tokens:
            extra["max_completion_tokens"] = self.config.max_tokens
        with self._errors():
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, *({"role": t.role, "content": t.text} for t in turns)],
                temperature=self.config.temperature,
                **extra,
            )
        choice = response.choices[0]
        return Reply(_strip_thinking(choice.message.content or ""), note=_CUT_OFF if choice.finish_reason == "length" else None)


class OllamaBackend(Backend):
    vendor = "ollama"

    MIN_CONTEXT = 8_192
    REPLY_ROOM = 4_096

    def __init__(self, model: str, config: Config, host: str | None = None) -> None:
        super().__init__(model, config)
        self.host = host
        self.client = ollama.Client(host=host)
        self.context_limit: int | None = None

    @property
    def where(self) -> str:
        return self.host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"

    @contextmanager
    def _errors(self) -> Iterator[None]:
        try:
            yield
        except ollama.ResponseError as exc:
            raise self._response_error(exc) from exc
        except (ConnectionError, httpx.ConnectError) as exc:
            raise AppError(
                f"Can't connect to Ollama at {self.where}.",
                "Start Ollama (open the Ollama app, or run `ollama serve` in another terminal), "
                "or install it from https://ollama.com/download.",
                kind="network",
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(f"The request to Ollama failed ({type(exc).__name__}).", "Check that Ollama is running, then try again.", kind="network") from exc

    def _response_error(self, exc: ollama.ResponseError) -> AppError:
        detail, status = str(exc.error), exc.status_code
        low = detail.lower()
        if status == 404 or "not found" in low:
            return model_not_found("ollama", self.model, detail=detail)
        if status in (401, 403) or "unauthorized" in low or "sign in" in low or "signin" in low:
            return AppError(
                f"Ollama needs you to sign in to use '{self.model}' ({detail}).",
                "Cloud models run on ollama.com: run `ollama signin` in a terminal, or pick a local model with /change-model.",
                kind="auth",
            )
        if "does not support" in low:
            return AppError(f"'{self.model}' can't be used for chat ({detail}).", "Pick a chat model: /models, then /change-model <name>.", kind="model")
        if "memory" in low:
            return AppError(f"Not enough memory to run '{self.model}' ({detail}).", "Pick a smaller model with /change-model, or close other apps.", kind="limit")
        return AppError(f"Ollama error: {detail} (HTTP {status}).", "Check the model with /models, or look at the Ollama logs.")

    def list_models(self) -> list[ModelInfo]:
        with self._errors():
            listed = self.client.list().models
        return [ModelInfo(m.model, _human_size(m.size)) for m in listed if m.model]

    def check(self) -> None:
        super().check()
        with self._errors():
            info = self.client.show(self.model)
        capabilities = list(info.capabilities or [])
        if capabilities and "completion" not in capabilities:
            raise AppError(
                f"'{self.model}' is an {'/'.join(capabilities)} model, so it can't chat.",
                "Pick a chat model: /models, then /change-model <name>.",
                kind="model",
            )
        lengths = [v for k, v in (info.modelinfo or {}).items() if k.endswith(".context_length") and isinstance(v, int)]
        self.context_limit = max(lengths) if lengths else None

    def _context_size(self, messages: list[dict[str, str]]) -> int:
        """Ollama silently cuts off prompts longer than its context window (num_ctx),
        which would drop the transcript - so size the window to fit the conversation."""
        estimated = sum(len(m["content"]) for m in messages) // 4  # ~4 characters per token
        if self.context_limit and estimated > self.context_limit:
            raise AppError(
                f"This conversation (~{estimated:,} tokens) is longer than '{self.model}' can read ({self.context_limit:,} tokens).",
                "Pick a model with a bigger context window (/models, /change-model), try a shorter video, or switch vendor.",
                kind="limit",
            )
        wanted = int(estimated * 1.25) + self.REPLY_ROOM
        size = max(self.MIN_CONTEXT, -(-wanted // 2048) * 2048)
        return min(size, self.context_limit) if self.context_limit else size

    def chat(self, system: str, turns: list[Turn]) -> Reply:
        messages = [{"role": "system", "content": system}, *({"role": t.role, "content": t.text} for t in turns)]
        options: dict[str, Any] = {"temperature": self.config.temperature, "num_ctx": self._context_size(messages)}
        if self.config.max_tokens:
            options["num_predict"] = self.config.max_tokens
        with self._errors():
            response = self.client.chat(model=self.model, messages=messages, options=options)
        return Reply(_strip_thinking(response.message.content or ""), note=_CUT_OFF if response.done_reason == "length" else None)


def _human_size(size: int | None) -> str:
    if not size or size < 1_000_000:
        return ""
    return f"{size / 1e9:.1f} GB" if size >= 1e9 else f"{size / 1e6:.0f} MB"


def make_backend(config: Config, vendor: Vendor | None = None, *, model: str | None = None, api_key: str | None = None) -> Backend:
    """Build the backend for `vendor` (default: the selected one).

    Raises AppError if the vendor is unknown or its API key is missing. It does
    not contact the vendor - call check() for that.
    """
    vendor = vendor or config.vendor
    if vendor not in VENDORS:
        raise AppError(f"Unknown vendor '{vendor}'.", f"Choose one of: {', '.join(VENDORS)} (/change-vendor).", kind="config")
    settings = config.settings_for(vendor)
    model = model or settings.model
    if vendor == "ollama":
        return OllamaBackend(model, config, host=settings.host)

    key = api_key or api_key_for(config, vendor)[0]
    if not key:
        info = VENDOR_INFO[vendor]
        raise AppError(
            f"No API key saved for {info.label}.",
            f"Run /add-api-key to add yours (create one at {info.key_url}), or set the {info.env_var} environment variable.",
            kind="config",
        )
    if vendor == "anthropic":
        return AnthropicBackend(model, config, key)
    return GroqBackend(model, config, key)
