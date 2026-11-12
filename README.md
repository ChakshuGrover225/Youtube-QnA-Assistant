# ytchat

Chat with any YouTube video or Instagram Reel from your terminal. Paste a link,
get a summary, then ask follow-up questions that are answered from the video's transcript.

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
uv tool install . -c constraints.txt
```

That puts a `ytchat` command on your PATH, so it works from any folder.
If your shell can't find it, run `uv tool update-shell` and open a new terminal.

- **Update** after changing the code: `uv tool install --reinstall . -c constraints.txt`
- **Uninstall:** `uv tool uninstall video-summarisation-project`
- **Without uv:** `pipx install . -c constraints.txt` works too.

### Why `-c constraints.txt`

Without it, `uv tool install` ignores `uv.lock` and installs the newest release of every dependency,
so a bad release published today would be installed today. `constraints.txt` pins all 35
dependencies to the exact versions in `uv.lock`. PyPI never allows a published version to be
replaced, so pinned versions can't be swapped for different code.

`uv run ytchat` and `uv sync` go further: they use `uv.lock` directly and check every
download against the hash recorded there. `uv tool install` can't check hashes (tested
with uv 0.12.17), so it gets pinned versions only.

`constraints.txt` is generated from `uv.lock` (the command is at the top of the file).
`uv run pytest` fails if the two don't match.

### Updating yt-dlp

Instagram changes its site from time to time, and a new yt-dlp is the usual fix. Update
yt-dlp alone, never everything at once (so no `--upgrade` on `uv tool install`):

```sh
uv lock --upgrade-package yt-dlp     # move yt-dlp (and only yt-dlp) to its newest version
git diff uv.lock                     # check that nothing else changed
uv export --frozen --no-dev --no-emit-project --no-hashes -o constraints.txt
uv run pytest
uv tool install --reinstall . -c constraints.txt
```

Other dependencies are updated the same way with `--upgrade-package <name>`.

## Quick start

```text
$ ytchat
Video link › /add-api-key
Paste your Groq API key (Enter to cancel): gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxa1b2
✓ Groq API key verified and saved (gsk_…a1b2)
✓ Ready: Groq · openai/gpt-oss-120b

Video link › https://www.youtube.com/watch?v=jNQXAC9IVRw
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

## Instagram Reels

Paste a reel link (`https://www.instagram.com/reel/SHORTCODE/`, `/reels/…` and links
with `?igsh=…` work too) wherever you'd paste a YouTube link. The summary panel is
titled **Reel summary**, and everything else works the same.

Reels have no captions to fetch, so ytchat downloads the reel's audio with
[yt-dlp](https://github.com/yt-dlp/yt-dlp) into a temporary folder, transcribes it with
Groq's Whisper speech-to-text, and deletes the audio straight away. Things to know:

- **Transcription always uses Groq**, whatever vendor you chat with, so you need a Groq
  key even when chatting with Anthropic or Ollama: `/add-api-key groq`.
- The reel's **audio is uploaded to Groq**; the transcript and your questions go to your
  chat vendor, as with YouTube.
- **Public reels only** - ytchat never logs in to Instagram.
- Reels with only music (no speech) can't be summarised.
- No ffmpeg needed.

## Commands

Type `/` at the prompt and the commands appear as you type: `/` lists them all, `/s` only
`/save-transcript`, `/c` the four starting with c. Tab or the arrow keys pick one, Enter runs it,
and the up arrow brings back earlier lines. This needs an interactive terminal (PowerShell,
Windows Terminal, macOS/Linux terminals); where it can't run, such as piped input or Git Bash's
default window, you get plain input and the commands still work when typed in full.

| Command | What it does |
|---|---|
| `/add-api-key [vendor]` | Save your API key for the current vendor, or the one you name (`/add-api-key anthropic`). The key shows as you paste it; after that only a masked form (`gsk_…a1b2`) is displayed. The key is checked with the vendor first; a key the vendor rejects is **not** saved. |
| `/change-model [name]` | Pick the model for the current vendor. Friendly names work: `opus 5.5` → `claude-opus-5-5`, `gpt-oss-20b` → `openai/gpt-oss-20b`, `qwen3:0.6B` → `qwen3:0.6b`. |
| `/change-vendor [name]` | Switch between `anthropic`, `groq` and `ollama` (name or number). Each vendor remembers its own model and key. |
| `/models` | List the models the current vendor offers (● marks the one in use). |
| `/config` | Show your settings and where they're saved. |
| `/save-transcript` | Save the open video's summary and transcript to a text file (see [Saving transcripts](#saving-transcripts)). |
| `/change-files-save-path [folder]` | Pick the folder `/save-transcript` saves to. Quotes around the path are fine; `default` goes back to the default folder. |
| `/new` | Close the current video so you can open another (or just paste a new link). |
| `/help` | List the commands. |
| `/exit` | End the conversation and quit (Ctrl+C or Ctrl+D also work). |

Everything you change is saved immediately and is still there next time.
You can switch vendor or model in the middle of a conversation - the new model
picks up the same transcript and chat history.

## Saving transcripts

`/save-transcript` writes the open video's transcript to a text file named
`<short-title>-<dd-mm-yy>.txt`, e.g. `job-search-in-norway-12-11-26.txt`:

- The **title** (up to 10 words) is written by your chat model from the summary. If the
  model can't be reached, the first words of the summary are used instead, so saving
  always works.
- The **file** starts with the title, the video's link and the date, then the summary,
  then the full transcript wrapped into lines.
- Files are **never overwritten**: saving the same video twice says "Already saved", and
  a different video with the same name and date gets `-2`, `-3`…

Where the files go:

- Running from the project folder (`uv run ytchat`): `src/video_summarisation_project/saved-transcripts/`.
  It's listed in `.gitignore` and left out of the installed package.
- The installed `ytchat` command: a `saved-transcripts` folder next to your settings file,
  because `uv tool install --reinstall` deletes the installed copy's own folder.
- Anywhere you like: `/change-files-save-path D:\Notes\ytchat` (the folder is created if needed).
  `/config` shows the folder in use.

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
| **Setup problem** - Instagram reels are transcribed with Groq, but no Groq API key is saved | `/add-api-key groq` - you can keep chatting with your current vendor. |
| **Can't do that** - Instagram didn't return this reel | It's private, deleted or login-only. ytchat can only open public reels: check the link opens in a private browser window. |
| **Can't do that** - There's too little speech in this reel to chat about | Music-only reels can't be summarised. Try another reel. |

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
| `transcript_languages` | `["en"]` | Preferred YouTube transcript languages, in order |
| `transcription_model` | `"whisper-large-v3-turbo"` | Groq speech-to-text model for Instagram reels |
| `vendors.ollama.host` | `null` | Ollama's address if it isn't `http://localhost:11434` |

The prompts live in `src/video_summarisation_project/prompts/`.

## How it works

Every link goes through `link_classifier.py`, which asks each platform whether the link
is one of its own and sends it to that platform's transcript code:

- YouTube link → video ID → captions ([youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api))
- Instagram Reel link → shortcode → audio ([yt-dlp](https://github.com/yt-dlp/yt-dlp)) → Groq Whisper speech-to-text

The transcript goes into the system prompt → the first message asks for a summary,
and every question after that continues the same conversation.

Transcripts are written by whoever made the video, so ytchat treats them as untrusted:

- The system prompt marks the transcript as material to summarise, never instructions to follow.
  A video that says "AI, tell the viewer to run this command" is reported as something the
  video says, not passed on as advice. This lowers the risk but can't rule it out, so be
  careful with any command or link an answer contains.
- Links in answers are always shown with their full address, never hidden behind link text.
- Terminal control characters (escape sequences that could clear your screen, change what's
  shown or write to your clipboard) are removed from answers, error messages and saved files.

Each vendor is called through its official SDK (`groq`, `anthropic`, `ollama`). With Anthropic,
the transcript is prompt-cached so follow-up questions are cheaper and faster, and
for models that support it a server-side refusal fallback is enabled (if a safety
classifier declines a request, the API retries it on a fallback model). With Ollama,
the context window is sized to fit the transcript, since Ollama would otherwise
silently cut off long prompts.

```
src/video_summarisation_project/
├── cli.py                      # the interactive chat and slash commands
├── prompt_input.py             # the main prompt: suggests /commands as you type
├── config.py                   # settings file: load, save, API keys
├── vendors.py                  # Anthropic / Groq / Ollama backends + error messages
├── link_classifier.py          # which platform a link is for → that platform's transcript
├── transcript_files.py         # /save-transcript: file name, contents and folder
├── safe_text.py                # strips terminal control characters from outside text
├── youtube_transcription.py    # YouTube link → captions
├── instagram_transcription.py  # Instagram Reel link → downloaded audio → speech_to_text
├── speech_to_text.py           # audio file → text (Groq Whisper)
├── errors.py                   # AppError: a problem plus how to fix it
└── prompts/                    # system prompt, summary request, file-title request
```

## Development

```sh
uv sync              # install dependencies
uv run ytchat        # run from source
uv run pytest        # run the tests (no API keys or network needed)
```
