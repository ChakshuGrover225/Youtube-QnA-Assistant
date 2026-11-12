# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`ytchat` is an interactive terminal app: paste a YouTube link, get a summary, then ask follow-up questions answered from the video's transcript. It supports three LLM vendors (Groq is the default, then Anthropic and Ollama), each called through its official SDK. Distribution name is `video-summarisation-project`, import package is `video_summarisation_project`, and the console script is `ytchat = video_summarisation_project.cli:main`. Python ≥ 3.13, managed with `uv` (build backend `uv_build`).

## Commands

Run from this folder (the repo root):

```sh
uv sync                                              # install deps into .venv
uv run ytchat ["https://youtu.be/VIDEO_ID"]          # run from source (or: uv run python -m video_summarisation_project)
uv run pytest                                        # full suite, no API keys or network needed
uv run pytest tests/test_vendors.py                  # one file
uv run pytest "tests/test_vendors.py::test_guess_vendor"   # one test
uv run pytest -k change_model                        # by name pattern
uv tool install --reinstall .                        # refresh the globally installed `ytchat` after code changes
```

No linter, formatter or type checker is configured.

## Architecture

The code is in `src/video_summarisation_project/`: `cli.py`, `vendors.py`, `config.py`, `transcript.py`, `errors.py`, plus `prompts/*.md`, which are loaded with `importlib.resources`.

**Input routing (`cli.App.run`).** A line starting with `/` is a slash command. A YouTube link, or any line typed while no video is open, goes to `open_video`. Everything else goes to `ask`. The slash commands are listed in two places, `COMMANDS` (the help text) and `App._commands` (the handlers), so a new command must be added to both.

**Backends (`vendors.py`).** `Backend` is an ABC with three methods: `list_models()`, `check()` and `chat(system, turns)`.
- `make_backend()` builds a backend without contacting anything. It raises `AppError(kind="config")` when the API key is missing.
- `check()` makes the network call. It runs `resolve_model` against `list_models()`, which both validates the model and corrects its exact spelling.
- `App.backend()` caches one checked backend. Every settings change (`_save`, `_store_key`) resets the cache to `None`, so the next use re-checks.
- `open_video` calls `backend()` *before* fetching the transcript, so setup problems show up before anything is downloaded.

**Conversation model.**
- The transcript lives in the system prompt: `chat_system.md`, then the optional `additional_prompt`, then `## Transcript\n<text>`.
- The summary request (`summary_request.md`) is sent as the first user turn, so the summary becomes part of the chat history.
- `Turn` is vendor-neutral. Assistant turns also keep the vendor's `raw` response and `raw_vendor`.
- `AnthropicBackend` replays `raw` content blocks, including thinking blocks with signatures, only when `raw_vendor == "anthropic"`. Turns from other vendors are sent as plain text. This is what lets the user switch vendor or model mid-conversation.
- `App._complete` pops the pending user turn on *any* exception, including Ctrl+C, so the history never contains an unanswered question.

**Errors.** Every problem shown to the user is an `AppError(problem, fix, kind)`. The `kind` field does two jobs:
- It sets the panel title, through `_ERROR_TITLES` in `cli.py`.
- It drives control flow. `_store_key` refuses to save a key only when the error kind is `"auth"`; on any other failure it saves the key as "not verified". `cmd_change_model` refuses on `"model"` and saves an unverified model otherwise.

SDK errors are translated in three places:
- Anthropic and Groq: `_sdk_errors`, then `http_error(status, detail)`. The two SDKs share the same error class names.
- Ollama: `OllamaBackend._errors` and `_response_error`.
- Transcripts: `_TRANSCRIPT_ERRORS` in `transcript.py`, keyed by youtube-transcript-api exception *class name*.

Tests assert on this problem/fix wording, so rewording a message usually means updating a test.

**Model names.**
- `normalize_model_name` turns friendly Claude names into IDs (`opus 5.5` → `claude-opus-5-5`, via the `_CLAUDE_NAME` regex).
- `resolve_model` matches case-insensitively and accepts shorthands: Claude display names, Groq IDs without the `org/` prefix, and Ollama names without `:latest`.
- `guess_vendor` produces the "this looks like another vendor's model" hints.

**Vendor-specific behaviour.**
- **Anthropic** uses `client.beta.messages.create` with top-level `cache_control: ephemeral`, which caches the transcript-heavy system prompt.
  - It never sends `temperature`, because current Claude models reject it.
  - `max_tokens` defaults to 16,000, since thinking counts toward it.
  - The server-side fallback beta is added only for models in `FALLBACK_MODELS`.
  - `stop_reason == "refusal"` becomes an `AppError`.
- **Groq** uses `max_completion_tokens` and `temperature`.
- **Ollama** needs special handling in two places:
  - It silently truncates long prompts, so `_context_size` sets `num_ctx` from a ~4 chars/token estimate and raises a `"limit"` error when the conversation exceeds the model's context length.
  - `check()` also rejects models that can't chat, such as embedding models.
- Groq and Ollama replies pass through `_strip_thinking`, which removes `<think>…</think>` tags.

**Config (`config.py`).**
- A pydantic `Config` is saved as JSON in the user config dir (`%APPDATA%\ytchat\config.json` or `~/.config/ytchat/config.json`). `YTCHAT_CONFIG_DIR` overrides the location.
- It is saved immediately on every change, using an atomic write through a `.tmp` file.
- Each vendor has its own `VendorSettings` (model, api_key, Ollama host).
- A saved key takes precedence over `GROQ_API_KEY` / `ANTHROPIC_API_KEY` (see `api_key_for`).
- `VENDOR_INFO` holds per-vendor metadata: label, default model, key prefix, env var and URLs.
- Adding a vendor touches:
  - the `Vendor` Literal
  - `VENDOR_INFO`
  - a `VendorTable` field
  - a `Backend` subclass
  - a branch in `make_backend`

**Windows quirks handled in `cli.py`.** `_clean` strips the BOM that PowerShell adds when piping input. `_use_utf8_when_piped` reconfigures stdout and stderr so rich's box characters survive non-TTY output.

## Tests

- `conftest.py` has an autouse fixture that points `YTCHAT_CONFIG_DIR` at a temp folder and unsets `GROQ_API_KEY`, `ANTHROPIC_API_KEY` and `OLLAMA_HOST`. Tests never touch the real config.
- `test_cli.py` drives a real `cli.App` with scripted input by replacing `console.input`. The `fake_vendor` fixture monkeypatches `vendors.make_backend` and `cli.fetch_transcript`. This only works because `cli.py` does `from . import vendors` and calls `vendors.make_backend(...)` through the module. Keep that access pattern, or the patch stops applying.
- `test_anthropic.py` runs the real `AnthropicBackend` against a mocked transport (`anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(...))`, passed in through the constructor's `http_client` parameter) and checks the outgoing request JSON. The Anthropic SDK uses `httpx2`, a transitive dependency, not `httpx`.
- API keys are deliberately entered with *visible* input. `test_api_key_stays_visible_while_pasting` asserts `password=False`.

## Docs

`README.md` (user reference) and `startupGuide.md` (beginner walkthrough) copy the slash commands, error titles and messages, and settings tables word for word. Update them when those change. `startupGuide.md` is already out of date: it still says the key is hidden while pasting.

## `src/logic/` is a legacy prototype

`src/logic/` (`summarisation_pipeline.py`, `settings.py`, `prompt_library/`) is the earlier Groq-only script, built on `langchain-groq` and `pydantic-settings`. Neither of those is in `pyproject.toml` or `uv.lock`, so it does not run after `uv sync`. It isn't part of the installed package and has no tests. `.env` / `.env.example` exist only for this script; `ytchat` never reads `.env`. It duplicates `extract_video_id` and `fetch_transcript`. Don't change it when changing ytchat's behaviour.
