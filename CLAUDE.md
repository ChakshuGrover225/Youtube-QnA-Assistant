# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`ytchat` is an interactive terminal app: paste a YouTube or Instagram Reel link, get a summary, then ask follow-up questions answered from the video's transcript. It supports three LLM vendors (Groq is the default, then Anthropic and Ollama), each called through its official SDK. Distribution name is `video-summarisation-project`, import package is `video_summarisation_project`, and the console script is `ytchat = video_summarisation_project.cli:main`. Python ≥ 3.13, managed with `uv` (build backend `uv_build`).

## Commands

Run from this folder (the repo root):

```sh
uv sync                                              # install deps into .venv
uv run ytchat ["https://youtu.be/VIDEO_ID"]          # run from source (or: uv run python -m video_summarisation_project)
uv run pytest                                        # full suite, no API keys or network needed
uv run pytest tests/test_vendors.py                  # one file
uv run pytest "tests/test_vendors.py::test_guess_vendor"   # one test
uv run pytest -k change_model                        # by name pattern
uv tool install --reinstall . -c constraints.txt     # refresh the globally installed `ytchat` after code changes
uv export --frozen --no-dev --no-emit-project --no-hashes -o constraints.txt   # after any change to uv.lock
```

No linter, formatter or type checker is configured.

**Dependencies are pinned for the global install.** `uv tool install` ignores `uv.lock`, so the install commands pass `-c constraints.txt`, which `uv export` generates from the lock. `tests/test_constraints.py` fails when the two differ, and when a doc's install command lacks `-c constraints.txt` or uses a blanket `--upgrade`. Update one dependency at a time with `uv lock --upgrade-package <name>`, then re-export. `uv tool install` doesn't check hashes; `uv sync`/`uv run` do (from `uv.lock`). A `[tool.uv] exclude-newer` cooldown was considered but not added: `anthropic>=2.8.0` was newer than 7 days, so the project wouldn't resolve.

## Architecture

The code is in `src/video_summarisation_project/`: `cli.py`, `vendors.py`, `config.py`, `link_classifier.py`, `youtube_transcription.py`, `instagram_transcription.py`, `speech_to_text.py`, `transcript_files.py`, `prompt_input.py`, `safe_text.py`, `errors.py`, plus `prompts/*.md`, which are loaded with `importlib.resources`.

**Input routing (`cli.App.run`).** The main prompt is read by `App.read_line`: in a real terminal that's `prompt_input.terminal_reader`, a prompt_toolkit session whose `SlashCommandCompleter` suggests `COMMANDS` while you type (prefix match; nothing once an argument is being typed). It renders the rich-markup prompt to ANSI with `console.capture()`. With no TTY (pipes, tests, Git Bash's mintty) it's `None` and `console.input` is used. Sub-prompts (`_ask`, e.g. pasting a key) always use `console.input`. A line starting with `/` is a slash command. A line that `classify()` recognises as a link, or any line typed while no video is open, goes to `open_video`. Everything else goes to `ask`. The slash commands are listed in two places, `COMMANDS` (the help text and the suggestions) and `App._commands` (the handlers), so a new command must be added to both.

**Transcripts (`link_classifier.py`).** `cli.py` knows no platform. It calls only `classify(text) -> VideoLink | None` and `get_transcript(video, config, progress) -> str`.
- `PLATFORMS` is an ordered tuple of `Platform(name, noun, parse, fetch)`. `classify` returns the first platform whose `parse` accepts the link. `noun` ("video", "reel") fills the summary title and the rule.
- `parse` (`extract_video_id`, `extract_reel_shortcode`) runs on every typed line, so it must be fast, offline and never raise. Both parsers catch the `ValueError` that `urlparse` raises on input like `x[0]?`.
- `fetch` may be slow and raises only `AppError`. `progress(text)` updates the spinner: `cli.py` passes `status.update` with the text escaped.
- Adding a platform: write `<platform>_transcription.py` with a parser and a fetcher, then add one `Platform` to `PLATFORMS`.
- **YouTube** (`youtube_transcription.py`) fetches captions with youtube-transcript-api, using `config.transcript_languages`.
- **Instagram** (`instagram_transcription.py`) accepts `instagram.com/reel(s)/<code>` and `instagram.com/<user>/reel/<code>` only (not `/p/`). It works on public reels only: no cookies, no login.
  - `fetch_reel_transcript` first calls `speech_to_text.require_groq_key`, so a missing key fails before anything is downloaded.
  - It then downloads the audio with yt-dlp (`download_audio`, an m4a audio-only format, so no ffmpeg) into a `TemporaryDirectory`, which is deleted after success, an error or Ctrl+C.
  - Then it calls `speech_to_text.transcribe`.
- **Speech-to-text** (`speech_to_text.py`) always uses Groq Whisper (`config.transcription_model`) with the Groq key, whatever the chat vendor is.
  - The language is auto-detected.
  - The audio is limited to 25 MB.
  - A result shorter than `MIN_WORDS` counts as "no speech", because Whisper invents "Thank you." on music.

**Saved transcripts (`transcript_files.py`).** `/save-transcript` writes `<title>-<dd-mm-yy>.txt`: a header (title, clean link from `VideoLink.url`, date), the summary, then the transcript wrapped at 100 characters.
- `Conversation` keeps the `transcript`; its `summary` property is `turns[1]`. The title comes from one extra `backend.chat` call (`App._file_title`, prompt `file_title.md`) that sends only the summary and is *not* added to the history. It is cached on `Conversation.title`. If the call fails, the file is named from the summary's first words (`title_from_summary`), so saving never depends on the network.
- `save` never overwrites: identical text counts as already saved, otherwise `-2`, `-3`...
- The folder is `config.files_save_path` (`/change-files-save-path`), or `default_save_dir()`: `saved-transcripts/` next to the code when running from source, or next to the config file when the package runs from `site-packages` (an installed copy is deleted by `uv tool install --reinstall`). The source folder is in `.gitignore` and in `source-exclude` in `pyproject.toml`, so saved files never end up in a build.

**Backends (`vendors.py`).** `Backend` is an ABC with three methods: `list_models()`, `check()` and `chat(system, turns)`.
- `make_backend()` builds a backend without contacting anything. It raises `AppError(kind="config")` when the API key is missing.
- `check()` makes the network call. It runs `resolve_model` against `list_models()`, which both validates the model and corrects its exact spelling.
- `App.backend()` caches one checked backend. Every settings change (`_save`, `_store_key`) resets the cache to `None`, so the next use re-checks.
- `open_video` calls `backend()` *before* fetching the transcript, so setup problems show up before anything is downloaded.

**Conversation model.**
- The transcript lives in the system prompt: `chat_system.md`, then the optional `additional_prompt`, then `<transcript>\n<text>\n</transcript>`.

**Untrusted text.** Transcripts are written by strangers, so three defences sit around them:
- *Prompt injection*: `chat_system.md` tells the model the transcript is data, never instructions, never to push commands, links or secrets because the transcript says so, and to write links as plain URLs. `_system_prompt` strips `<transcript>` tags from inside the transcript (`_TRANSCRIPT_TAG`) so it can't close the block early. `file_title.md` says the same for the summary. A live check on Groq (gpt-oss-120b and -20b) showed both models obeying an injected "run this PowerShell command" with the old prompt and neither with the new one. That lowers the risk; it doesn't make injection impossible.
- *Terminal control characters*: `safe_text.printable()` removes C0/C1 controls (incl. ESC; keeps `\n`, `\t`) and bidi overrides. It is applied to `AppError` problem/fix (in its constructor, so every print site is covered), model replies and notes (`_show_reply`), `/models` entries, and everything `transcript_files.render` writes. rich itself does not strip ESC.
- *Hidden links*: replies are rendered with `Markdown(..., hyperlinks=False)`, so a link's address is always printed, not just its text.
- The summary request (`summary_request.md`) is sent as the first user turn, so the summary becomes part of the chat history.
- `Turn` is vendor-neutral. Assistant turns also keep the vendor's `raw` response and `raw_vendor`.
- `AnthropicBackend` replays `raw` content blocks, including thinking blocks with signatures, only when `raw_vendor == "anthropic"`. Turns from other vendors are sent as plain text. This is what lets the user switch vendor or model mid-conversation.
- `App._complete` pops the pending user turn on *any* exception, including Ctrl+C, so the history never contains an unanswered question.

**Errors.** Every problem shown to the user is an `AppError(problem, fix, kind)`. The `kind` field does two jobs:
- It sets the panel title, through `_ERROR_TITLES` in `cli.py`.
- It drives control flow. `_store_key` refuses to save a key only when the error kind is `"auth"`; on any other failure it saves the key as "not verified". `cmd_change_model` refuses on `"model"` and saves an unverified model otherwise.

SDK and library errors are translated in five places:
- Anthropic and Groq chat: `_sdk_errors`, then `http_error(status, detail)`. The two SDKs share the same error class names.
- Ollama: `OllamaBackend._errors` and `_response_error`.
- YouTube transcripts: `_TRANSCRIPT_ERRORS` in `youtube_transcription.py`, keyed by youtube-transcript-api exception *class name*.
- Instagram downloads: `_download_error` in `instagram_transcription.py`, matched on yt-dlp's message text. Private, deleted and login-only reels all come back as "Instagram sent an empty media response".
- Speech-to-text: `_http_error` in `speech_to_text.py`. It doesn't reuse `http_error`, because that one's fixes (`/change-model`, plain `/add-api-key`) are about the *chat* vendor.

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
- `transcription_model` (default `whisper-large-v3-turbo`) is the Groq speech-to-text model for reels. It can only be changed by editing the file.
- Adding a vendor touches:
  - the `Vendor` Literal
  - `VENDOR_INFO`
  - a `VendorTable` field
  - a `Backend` subclass
  - a branch in `make_backend`

**Windows quirks handled in `cli.py`.** `_clean` strips the BOM that PowerShell adds when piping input. `_use_utf8_when_piped` reconfigures stdout and stderr so rich's box characters survive non-TTY output.

## Tests

- `conftest.py` has an autouse fixture that points `YTCHAT_CONFIG_DIR` at a temp folder and unsets `GROQ_API_KEY`, `ANTHROPIC_API_KEY` and `OLLAMA_HOST`. It also points `transcript_files._PACKAGE_DIR` at a temp folder, so `/save-transcript` tests never write into `src/`. Tests never touch the real config.
- `test_cli.py` drives a real `cli.App` with scripted input by replacing `console.input`. The `fake_vendor` fixture monkeypatches `vendors.make_backend` and `cli.get_transcript`, the one call from link to text.
  - Patching `vendors.make_backend` only works because `cli.py` does `from . import vendors` and calls `vendors.make_backend(...)` through the module. Keep that access pattern, or the patch stops applying.
  - Patching `cli.get_transcript` works because `cli.py` imports that name directly.
  - `FakeBackend.chat` answers the file-title request (system prompt `file_title.md`) with `FakeBackend.title`.
  - Long temp-folder paths wrap in the 120-column output; `flat(out)` removes wrapping and panel borders before matching.
  - To run the real reel pipeline in a CLI test, set `cli.get_transcript` back to `link_classifier.get_transcript`.
- `test_anthropic.py` runs the real `AnthropicBackend` against a mocked transport (`anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(...))`, passed in through the constructor's `http_client` parameter) and checks the outgoing request JSON. The Anthropic SDK uses `httpx2`, a transitive dependency, not `httpx`.
- `test_speech_to_text.py` does the same for Groq: `groq.DefaultHttpxClient(transport=httpx.MockTransport(...))`, passed as `transcribe(..., http_client=...)`. Groq uses plain `httpx`. The Groq client retries 429 and 5xx responses, so those cases are tested through `_http_error` directly.
- `test_instagram_transcription.py` replaces `yt_dlp.YoutubeDL` with a fake that writes `audio.m4a`. It points `tempfile.tempdir` at `tmp_path` to check that the temp folder is deleted.
- `test_prompt_input.py` drives a real prompt_toolkit session through `create_pipe_input()` + `DummyOutput()`. Suggestions are computed in the background, so `typed()` sends each keystroke group from a thread with a short pause; keys sent all at once arrive before the suggestions exist.
- API keys are deliberately entered with *visible* input. `test_api_key_stays_visible_while_pasting` asserts `password=False`.

## Docs

`README.md` (user reference) and `startupGuide.md` (beginner walkthrough) copy the slash commands, error titles and messages, and settings tables word for word. Update them when those change. `startupGuide.md` is already out of date: it still says the key is hidden while pasting.

## `src/logic/` is a legacy prototype

`src/logic/` (`summarisation_pipeline.py`, `settings.py`, `prompt_library/`) is the earlier Groq-only script, built on `langchain-groq` and `pydantic-settings`. Neither of those is in `pyproject.toml` or `uv.lock`, so it does not run after `uv sync`. It isn't part of the installed package and has no tests. `.env` / `.env.example` exist only for this script; `ytchat` never reads `.env`. It duplicates `extract_video_id` and `fetch_transcript`. Don't change it when changing ytchat's behaviour.
