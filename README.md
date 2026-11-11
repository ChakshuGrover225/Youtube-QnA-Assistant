# ytchat

Chat with any YouTube video from your terminal. Paste a link, get a summary,
then ask follow-up questions that are answered from the video's transcript.

Works with three LLM vendors - pick one and bring your own key:

| Vendor | What you need | Example models |
|---|---|---|
| **groq** (default) | A free API key from [console.groq.com/keys](https://console.groq.com/keys) | `openai/gpt-oss-120b`, `openai/gpt-oss-20b` |
| **anthropic** | An API key from [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys) | `opus 5.5`, `sonnet 5.5`, `haiku 5.5` |
| **ollama** | [Ollama](https://ollama.com/download) running on your computer - no key | `qwen3:0.6b`, `llama3.2` |

No keys ship with this project: everyone who uses it adds their own with `/add-api-key`.

**New here?** Follow the step-by-step [startup guide](startupGuide.md) - it goes from nothing installed to your first chat.

## Install

You need [uv](https://docs.astral.sh/uv/getting-started/installation/). It also installs Python 3.13 for you if needed.

```sh
# from this folder
uv tool install .
```

That puts a `ytchat` command on your PATH, so it works from any folder.
If your shell can't find it, run `uv tool update-shell` and open a new terminal.

- **Update** after changing the code: `uv tool install --reinstall .`
- **Uninstall:** `uv tool uninstall video-summarisation-project`
- **Without uv:** `pipx install .` works too.

## Quick start

```text
$ ytchat
YouTube link › /add-api-key
Paste your Groq API key (input hidden, Enter to cancel):
✓ Groq API key verified and saved (gsk_…ipOQ)
✓ Ready: Groq · openai/gpt-oss-120b

YouTube link › https://www.youtube.com/watch?v=jNQXAC9IVRw
✓ Transcript fetched (39 words)
┌─ Video summary · jNQXAC9IVRw ──────────────────────────────┐
│ TL;DR: A short clip of the narrator in front of elephants…  │
└────────────────────────────────── groq · openai/gpt-oss-120b ┘
You › What does he say is cool about them?
┌─ Assistant ─────────────────────────────────────────────────┐
│ That they have really, really long trunks.                  │
└─────────────────────────────────────────────────────────────┘
You › /exit
Conversation ended. Bye!
```

You can also open a video straight away: `ytchat "https://youtu.be/VIDEO_ID"`
(keep the quotes - `&` in links means something to your shell).

## Commands

| Command | What it does |
|---|---|
| `/add-api-key [vendor]` | Save your API key for the current vendor, or the one you name (`/add-api-key anthropic`). Input is hidden. The key is checked with the vendor first; a key the vendor rejects is **not** saved. |
| `/change-model [name]` | Pick the model for the current vendor. Friendly names work: `opus 5.5` → `claude-opus-5-5`, `gpt-oss-20b` → `openai/gpt-oss-20b`, `qwen3:0.6B` → `qwen3:0.6b`. |
| `/change-vendor [name]` | Switch between `anthropic`, `groq` and `ollama` (name or number). Each vendor remembers its own model and key. |
| `/models` | List the models the current vendor offers (● marks the one in use). |
| `/config` | Show your settings and where they're saved. |
| `/new` | Close the current video so you can open another (or just paste a new link). |
| `/help` | List the commands. |
| `/exit` | End the conversation and quit (Ctrl+C or Ctrl+D also work). |

Everything you change is saved immediately and is still there next time.
You can switch vendor or model in the middle of a conversation - the new model
picks up the same transcript and chat history.

## When something's wrong

ytchat checks your vendor, model and key before it downloads anything, and
every problem comes with the fix. For example:

| You'll see | What to do |
|---|---|
| **Setup problem** - No API key saved for Groq | `/add-api-key` |
| **API key problem** - Groq rejected your API key | Paste a valid key with `/add-api-key`. Keys from the wrong vendor are spotted (`sk-ant-…` is Anthropic, `gsk_…` is Groq). |
| **Model problem** - Model 'x' isn't available on Groq | `/models`, then `/change-model <name>`. Typos get a "Did you mean…?", and a model from another vendor (e.g. `opus 5.5` on Groq) tells you which `/change-vendor` to run. |
| **Model problem** - Model 'x' isn't installed in Ollama | `ollama pull x`, or pick an installed model. Embedding-only models (e.g. `nomic-embed-text`) are refused, since they can't chat. |
| **Connection problem** - Can't connect to Ollama | Open the Ollama app or run `ollama serve`. |
| **Limit reached** - too long / rate limit | Long videos can exceed a model's context window or Groq's free tokens-per-minute limit. Try a model with bigger limits, a shorter video, or another vendor. |
| **Can't do that** - Captions are turned off for this video | ytchat needs a video with captions (auto-generated ones are fine). |

## Settings

Settings are kept in one JSON file in your user folder (`/config` shows the exact path):

- Windows: `%APPDATA%\ytchat\config.json`
- macOS / Linux: `~/.config/ytchat/config.json`

Set `YTCHAT_CONFIG_DIR` to keep it somewhere else. API keys are stored in this file
in plain text, like most CLI tools, so don't share it. If no key is saved, ytchat
falls back to the `GROQ_API_KEY` / `ANTHROPIC_API_KEY` environment variables.

Advanced settings you can edit in that file:

| Setting | Default | Meaning |
|---|---|---|
| `temperature` | `0.3` | 0 = focused, higher = more varied (Groq and Ollama; current Claude models don't take it) |
| `max_tokens` | `null` | Cap on each answer's length. `null` = vendor default (16,000 for Anthropic) |
| `additional_prompt` | `""` | Extra instructions, e.g. `"Keep every answer under 100 words."` |
| `transcript_languages` | `["en"]` | Preferred transcript languages, in order |
| `vendors.ollama.host` | `null` | Ollama's address if it isn't `http://localhost:11434` |

The prompts live in `src/video_summarisation_project/prompts/`.

## How it works

YouTube link → video ID → transcript ([youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api))
→ the transcript goes into the system prompt → the first message asks for a summary,
and every question after that continues the same conversation.

Each vendor is called through its official SDK (`groq`, `anthropic`, `ollama`). With Anthropic,
the transcript is prompt-cached so follow-up questions are cheaper and faster, and
for models that support it a server-side refusal fallback is enabled (if a safety
classifier declines a request, the API retries it on a fallback model). With Ollama,
the context window is sized to fit the transcript, since Ollama would otherwise
silently cut off long prompts.

```
src/video_summarisation_project/
├── cli.py          # the interactive chat and slash commands
├── config.py       # settings file: load, save, API keys
├── vendors.py      # Anthropic / Groq / Ollama backends + error messages
├── transcript.py   # YouTube link → transcript
├── errors.py       # AppError: a problem plus how to fix it
└── prompts/        # system prompt and summary request
```

## Development

```sh
uv sync              # install dependencies
uv run ytchat        # run from source
uv run pytest        # run the tests (no API keys or network needed)
```
