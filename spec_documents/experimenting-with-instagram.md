# Spec: Chat with an Instagram Reel

> **How to fill in this template**
>
> - Replace every `TBD` with a concrete value or decision. Before handing this spec to Claude Code, search the file for `TBD`. The count must be **0**.
> - `<!-- comments -->` hold guidance and examples. Claude Code reads them too, so delete any that no longer match your decisions.
> - Sections marked **(pre-filled)** describe how ytchat works today, taken from the code. Check them, and only change them if the code has changed.
> - In decision lists, tick exactly one box (`[x]`) unless the list says *tick all that apply*.
> - Write requirements with **MUST**, **MUST NOT**, **SHOULD** and **MAY**. MUST means Claude Code may not deviate. SHOULD is the default unless the spec gives a reason not to.
> - Every requirement has an ID (G1, FR-3, E5, AC-7…) so tests, commits and reviews can point at it.

---

## 0. Document info

| Field | Value |
|---|---|
| Spec ID | `SPEC-001-instagram-reels` |
| Title | Chat with an Instagram Reel |
| Author | TBD |
| Status | Draft <!-- Draft → Ready for implementation → Implemented --> |
| Spec version | 0.1 |
| Last updated | TBD |
| Target ytchat version | TBD <!-- current version is 0.1.0 in pyproject.toml --> |
| Reviewers | TBD |

---

## 1. Instructions for the implementer (Claude Code) (pre-filled)

1. This spec is the source of truth for **what** to build. `CLAUDE.md` describes how the code works **today**.
2. If a `TBD` remains, a requirement is ambiguous, or the spec contradicts the code: **stop and ask**. Do not guess.
3. Build in the milestone order of §17. After each milestone, `uv run pytest` MUST pass.
4. YouTube behaviour MUST NOT change, except for the texts decided in §6.2. Existing tests MUST pass unchanged, except those listed in §15.5.
5. MUST NOT add dependencies beyond those listed in §9.2. Add them with `uv add` so `pyproject.toml` and `uv.lock` change together.
6. Every failure a user can hit MUST surface as `AppError(problem, fix, kind)` with the texts from §12, never as a traceback.
7. Tests MUST run without network access, API keys, an Instagram account, or ffmpeg.

---

## 2. Summary

TBD

<!-- 2–4 sentences. Example: "ytchat accepts an Instagram Reel link anywhere it accepts a YouTube link today. It downloads the reel's audio, transcribes it with <provider>, and runs the existing summary + Q&A conversation on that transcript, with the same commands, vendors and error style." -->

---

## 3. Background and motivation

- **Problem / who it's for:** TBD
- **Why now:** TBD
- **The key difference from YouTube (pre-filled):** YouTube videos come with captions, which `youtube-transcript-api` fetches as text without downloading the video. There is no supported way to fetch a transcript for an arbitrary Instagram Reel, so ytchat must **download the reel's audio and run speech-to-text (STT)** itself. Most of the new decisions, dependencies, costs and failure modes in this spec come from that.

---

## 4. Goals

<!-- Suggested from "do exactly what the YouTube flow does". Edit, delete or add. Each goal must be testable. -->

| ID | Goal |
|---|---|
| G1 | A user can paste an Instagram Reel link at the link prompt, at the `You ›` prompt, or as `ytchat "<link>"`, and get a summary followed by a Q&A conversation, exactly as with a YouTube link. |
| G2 | Answers come only from the reel's transcript, under the same system-prompt rules as YouTube. |
| G3 | All existing slash commands work during a reel conversation, including switching vendor or model mid-conversation without losing history. |
| G4 | Every failure (bad link, private reel, no speech, missing key…) shows a titled error panel with a fix, and the app keeps running. |
| G5 | Setup problems (chat vendor, model, key, STT prerequisites) are detected **before** anything is downloaded. |
| G6 | YouTube behaviour is unchanged. |
| G7 | TBD |

---

## 5. Non-goals

<!-- Things that will NOT be built now. Claude Code must not build them "while it's in there". Suggested list: edit it. -->

| ID | Non-goal |
|---|---|
| NG1 | Instagram Stories, Lives, Highlights, image posts and carousels. |
| NG2 | Saving the downloaded video or audio for the user. Media is temporary. |
| NG3 | Reading comments, likes, or any metadata beyond what D4 decides. |
| NG4 | Logging in to Instagram from inside ytchat with a username and password. |
| NG5 | Other platforms (TikTok, YouTube Shorts via another route, X, Facebook…). <!-- D7 may make them easier later --> |
| NG6 | Understanding the video frames (on-screen text, images). Audio only. |
| NG7 | Several reels in one conversation, or a batch mode. |
| NG8 | TBD |

---

## 6. Current behaviour to mirror (pre-filled)

### 6.1 The YouTube flow today

1. `cli.App.run` reads a line. A line starting with `/` goes to `handle_command`. If no video is open, **or** `extract_video_id(line)` returns an ID, the line goes to `open_video`. Otherwise it goes to `ask`.
2. `open_video(link)`:
   1. `extract_video_id(link)` returns the 11-character ID, or `open_video` raises `AppError(kind="input")` "That's not a YouTube video link".
   2. `self.backend()` builds and checks the chat backend (spinner `Checking <Vendor> · <model>...`) **before** any download.
   3. `fetch_transcript(video_id, config.transcript_languages)` runs under the spinner `Fetching the transcript for <id>...`.
   4. Prints `✓ Transcript fetched (N words)`.
   5. Builds `Conversation(video_id, system)`, where `system` is `prompts/chat_system.md`, then the optional `## Additional instructions`, then `## Transcript\n<text>`.
   6. `_complete(conversation, <prompts/summary_request.md>)` sends the summary request as the first user turn (spinner `Summarising with <model>...`).
   7. Shows the `Video summary · <id>` panel, then the rule `Ask anything about the video`.
   8. `self.conversation` is replaced **only after success**, so a failed open keeps the previous conversation.
3. `ask(question)` calls `_complete` and shows an `Assistant` panel. If the call fails, the question is removed from the history.
4. Errors are `AppError(problem, fix, kind)`. `kind` is one of `auth, model, config, network, limit, input, other` and selects the panel title: API key problem, Model problem, Setup problem, Connection problem, Limit reached, Can't do that, Something went wrong.

### 6.2 YouTube-specific text the user sees

<!-- Decide the new wording for each line. "Keep" is a valid answer. If you generalise a text, YouTube users see the change too, and the tests in the last column must be listed in §15.5. -->

| # | Where | Current text | New text | Asserted by test |
|---|---|---|---|---|
| T1 | `cli.py` `_banner` | `Chat with any YouTube video.` | TBD | — |
| T2 | `cli.py` `_banner` | `Paste a YouTube link to start · /help for commands · /exit to quit` | TBD | — |
| T3 | `cli.py` `run` | Prompt label `YouTube link ›` | TBD | — |
| T4 | `cli.py` `open_video` | `That's not a YouTube video link: <link>` and the fix with example links | TBD | `test_cli.py::test_invalid_link` |
| T5 | `cli.py` `open_video` | Spinner `Fetching the transcript for <id>...` | TBD | — |
| T6 | `cli.py` `open_video` | Panel title `Video summary · <id>` | TBD | `test_full_conversation_ends_with_exit`, `test_failed_question_keeps_the_conversation_going` |
| T7 | `cli.py` `open_video` | Rule `Ask anything about the video` | TBD | — |
| T8 | `cli.py` `cmd_help` | `Anything else you type is a question about the current video, or a YouTube link to open.` | TBD | — |
| T9 | `cli.py` `cmd_new` | `No video is open. Paste a YouTube link to start.` and `Closed the video. Paste another YouTube link.` | TBD | `test_new_and_unknown_commands` |
| T10 | `cli.py` `COMMANDS` | `/new`: `Drop the current video and open another one` | TBD | — |
| T11 | `cli.py` `main` | argparse description and `link` help mention YouTube | TBD | — |
| T12 | `prompts/chat_system.md` | `You are a helpful assistant answering questions about a YouTube video.` | TBD | — |
| T13 | `prompts/summary_request.md` | `Summarise this video. …` | TBD | `test_full_conversation_ends_with_exit` (expects `answer 1: Summarise this video.`) |
| T14 | `__init__.py` and `cli.py` docstrings, `pyproject.toml` `description` | "chat with any YouTube video" | TBD | — |

Also pre-filled: the fake backend in `test_cli.py` asserts that the system prompt contains `## Transcript\n<transcript>`. §8.5 MUST keep that heading directly followed by the transcript text, or that test must be listed in §15.5.

---

## 7. Key decisions (resolve these first)

<!-- Most later sections depend on these. Fill in "Decision" and "Why" for every one. -->

### D1. How to download the reel

- [ ] `yt-dlp`, through its Python API (`yt_dlp.YoutubeDL`) <!-- actively maintained, has an Instagram extractor, can fetch audio-only formats and read browser cookies -->
- [ ] `instaloader`
- [ ] Other: TBD

**Decision:** TBD · **Why:** TBD

<!-- Before deciding, try 3+ real public reels with the tool and no login. Instagram often refuses anonymous requests; see D5. -->

### D2. Speech-to-text provider and model

- [ ] Groq speech-to-text API (`client.audio.transcriptions.create` in the `groq` SDK that ytchat already uses). Model: TBD <!-- check console.groq.com docs for current Whisper models, accepted file types and size limits -->
- [ ] OpenAI transcription API. Model: TBD <!-- adds the `openai` dependency and a new key type -->
- [ ] Local Whisper (e.g. `faster-whisper`). Model size: TBD <!-- no key and no upload, but a large model download and slow on CPU -->
- [ ] Other: TBD

**Decision:** TBD · **Why:** TBD

### D3. How STT relates to the chat vendor

<!-- Today the user picks one chat vendor (groq, anthropic or ollama). Not all of them can transcribe audio. -->

- [ ] STT always uses one provider, whatever the chat vendor is. If it needs a key, reuse the key saved for that provider (e.g. the Groq key via `api_key_for(config, "groq")`).
- [ ] A new setting, `transcription_provider`, independent of the chat vendor, with its own key handling.
- [ ] Other: TBD

**Decision:** TBD · **Why:** TBD

- What happens when someone chatting with Anthropic or Ollama has no key for the STT provider? TBD <!-- e.g. error E8 with the fix "/add-api-key groq" -->

### D4. Use the reel's caption (post description) as context?

- [ ] No: transcript only, as with YouTube.
- [ ] Yes: add it to the system prompt under its own heading (§8.5).
- [ ] Only when the transcript is empty (e.g. music-only reels).

**Decision:** TBD · **Why:** TBD

### D5. Instagram authentication

- [ ] None: public reels only. Login-walled reels fail with E3.
- [ ] Cookies read from the user's browser (`yt-dlp` `cookiesfrombrowser`), browser chosen in config.
- [ ] Path to a cookies file (Netscape format) in config.

**Decision:** TBD · **Why:** TBD

<!-- Cookies are session credentials. See §14. -->

### D6. Limits

| Limit | Value | Behaviour when exceeded |
|---|---|---|
| Max reel duration | TBD seconds | TBD <!-- e.g. refuse before downloading, with E10 --> |
| Max audio size sent to STT | TBD MB | TBD <!-- must be within the STT provider's limit; or split into chunks? --> |
| Download timeout | TBD seconds | E12 |
| STT request timeout | TBD seconds | E13 |

### D7. Code structure

- [ ] **Generalise:** add a `Source` type (platform + id + url) and one module per platform (e.g. `sources/youtube.py`, `sources/instagram.py`). `cli.py` only talks to the source layer.
- [ ] **Add alongside:** new modules (e.g. `instagram.py`, `transcribe.py`) next to `transcript.py`. `cli.py` checks for a YouTube link first, then for an Instagram one.

**Decision:** TBD · **Why:** TBD

<!-- Generalising touches more code (Conversation.video_id, how tests patch cli.fetch_transcript) but makes other platforms easy later. "Add alongside" is smaller and leaves the YouTube code alone. -->

### D8. Prompts

- [ ] Make `chat_system.md` and `summary_request.md` platform-neutral and use them for both.
- [ ] Separate prompt files per platform (e.g. `prompts/instagram/chat_system.md`).
- [ ] One template with the platform name filled in (e.g. a `{platform}` placeholder).

**Decision:** TBD · **Why:** TBD

### D9. Reels with no speech (music only, silence)

- [ ] Show error E11 and open no conversation.
- [ ] Open the conversation using only the caption (requires D4 = yes).
- [ ] Other: TBD

**Decision:** TBD
**"No speech" means:** TBD <!-- empty transcript only, or fewer than N words? Whisper models can produce short invented text such as "Thank you." on music or silence, so consider a minimum word count. -->

### D10. Transcript language

- [ ] Let STT detect the language.
- [ ] Pass the first entry of `config.transcript_languages` to STT as a language hint.
- [ ] Translate to English during STT (only if the provider supports it).

**Decision:** TBD

<!-- summary_request.md already says "Respond in English, even if the transcript is not." -->

### D11. Caching

- [ ] None: every open re-downloads and re-transcribes (as YouTube does today).
- [ ] Cache transcripts on disk, keyed by shortcode, at path TBD, for TBD days.

**Decision:** TBD

### D12. ffmpeg

- [ ] Not required: download an audio stream in a format the STT API accepts as-is.
- [ ] Required: convert to TBD format before STT. Check with `shutil.which("ffmpeg")` during pre-flight (P3) and fail with E7 if it's missing.

**Decision:** TBD

<!-- Check which formats a reel offers (`yt-dlp -F <url>`) and which the STT API accepts. Avoiding ffmpeg keeps install as simple as today's `uv tool install .`. -->

---

## 8. Functional requirements

### 8.1 Accepted links

- **FR-1:** Leading and trailing whitespace is ignored. A link with whitespace inside it is rejected (same as YouTube).
- **FR-2:** A link without a scheme (`instagram.com/reel/…`) is accepted. `http://` is accepted: TBD
- **FR-3:** Host matching ignores case and a leading `www.`. Accepted hosts: TBD <!-- e.g. instagram.com, m.instagram.com; instagr.am? -->
- **FR-4:** Query strings (`?igsh=…`, `?utm_source=…`) and fragments are ignored.
- **FR-5:** Shortcode rule (exact regex): TBD <!-- shortcodes use A–Z a–z 0–9 _ - and their length varies. Collect 5+ real links before fixing the regex. YouTube uses ^[A-Za-z0-9_-]{11}$. -->
- **FR-6:** The parser returns the shortcode or `None`. It never raises and never makes a network call.

Each row below becomes one case of a parametrised test. Replace `SHORTCODE` with real shortcodes.

| Input | Expected result |
|---|---|
| `https://www.instagram.com/reel/SHORTCODE/` | `SHORTCODE` |
| `https://www.instagram.com/reel/SHORTCODE` | TBD |
| `https://www.instagram.com/reels/SHORTCODE/` | TBD |
| `https://www.instagram.com/reel/SHORTCODE/?igsh=abc123` | TBD |
| `instagram.com/reel/SHORTCODE/` | TBD |
| `https://m.instagram.com/reel/SHORTCODE/` | TBD |
| `https://www.instagram.com/<username>/reel/SHORTCODE/` | TBD |
| `https://www.instagram.com/p/SHORTCODE/` | TBD <!-- posts can be videos or images; see NG1 and E6 --> |
| `https://www.instagram.com/tv/SHORTCODE/` | TBD |
| `https://instagr.am/reel/SHORTCODE/` | TBD |
| `https://www.instagram.com/stories/<username>/1234567890/` | `None` |
| `https://www.instagram.com/<username>/` | `None` |
| `https://www.instagram.com/reel/` | `None` |
| `https://www.notinstagram.com/reel/SHORTCODE/` | `None` |
| `https://youtu.be/jNQXAC9IVRw` | `None` (YouTube parser handles it) |
| TBD | TBD |

### 8.2 Routing

- **FR-7:** At the link prompt, a reel link opens the reel.
- **FR-8:** At the `You ›` prompt, a reel link opens the reel and replaces the current conversation only if the open succeeds (same as a YouTube link, §6.1 step 2.8).
- **FR-9:** `ytchat "<reel link>"` opens the reel on start-up.
- **FR-10:** Order of checks for a line: TBD <!-- e.g. YouTube parser first, then Instagram. If neither matches and no conversation is open, show E1. -->
- **FR-11:** Any other line at `You ›` is a question (unchanged).

### 8.3 Processing pipeline

| Step | What happens | Spinner / status text | On failure |
|---|---|---|---|
| P1 | Parse the link into a shortcode (§8.1) | — | E1 |
| P2 | Check the chat backend with `self.backend()` (unchanged) | `Checking <Vendor> · <model>...` (existing) | existing errors |
| P3 | Check STT prerequisites: key (D3), ffmpeg (D12), download library importable | TBD | E7, E8 |
| P4 | Fetch reel info (duration, has audio, caption if D4) without downloading media | TBD | E2–E6, E10, E12, E14 |
| P5 | Download the audio into a temp folder (§10.5) | TBD <!-- e.g. "Downloading the reel's audio..." --> | E2–E5, E12, E14 |
| P6 | Transcribe | TBD <!-- e.g. "Transcribing with Groq · <model>..." --> | E9, E11, E13 |
| P7 | Delete the temp folder: always, including after an error or Ctrl+C | — | never shown |
| P8 | Print the transcript-ready line | TBD <!-- exact text, e.g. "✓ Transcript ready (N words)" --> | — |
| P9 | Build the system prompt (§8.5) and request the summary (`_complete`, unchanged) | TBD | existing errors |
| P10 | Show the summary panel (title from T6) and the rule (T7) | — | — |

- **FR-12:** P2 and P3 MUST finish before P4. Nothing is sent to Instagram until setup is OK.
- **FR-13:** Ctrl+C during P4–P9 prints `Cancelled.`, returns to the prompt, opens no conversation, and leaves no temp files.
- **FR-14:** Transcript clean-up rules: TBD <!-- e.g. join segments with single spaces, strip, no timestamps -->

### 8.4 Transcript format sent to the LLM

TBD

<!-- Plain text like YouTube? Or with timestamps ("[0:12] …") so questions like "when does she mention X" work? -->

### 8.5 System prompt structure

Write the exact layout. Example (replace):

```text
<contents of the chat system prompt file>

## Additional instructions          (only if additional_prompt is set)
<additional_prompt>

## Caption                          (only if D4 = yes and the reel has a caption)
<caption text>

## Transcript
<transcript text>
```

Final layout: TBD

### 8.6 Slash commands

| Command | Changes for reels? | Details |
|---|---|---|
| `/help` | TBD | T8, T10 |
| `/add-api-key` | TBD | <!-- If STT needs a key for a vendor that isn't the chat vendor, does `/add-api-key groq` cover it? --> |
| `/change-model` | TBD | <!-- chat model only, or the STT model too? --> |
| `/change-vendor` | TBD | |
| `/models` | TBD | |
| `/config` | TBD | <!-- show STT provider and model, cookie source --> |
| `/new` | TBD | T9 |
| `/exit` | No | |
| New command(s) | TBD | <!-- prefer none; e.g. /change-transcriber if STT is user-selectable --> |

### 8.7 Expected terminal session

Write the exact output of a successful run. Claude Code will reproduce it in a test with a faked transcript.

Example based on the YouTube session in `README.md` (replace):

```text
$ ytchat
YouTube link › https://www.instagram.com/reel/SHORTCODE/
✓ Transcript ready (142 words)
┌─ Reel summary · SHORTCODE ──────────────────────────┐
│ TL;DR: …                                            │
│  • …                                                │
└───────────────────────────── groq · openai/gpt-oss-120b ┘
──── Ask anything about the reel · /help for commands · /exit to quit ────

You › What product does she recommend?
┌─ Assistant ─────────────────────────────────────────┐
│ …                                                   │
└─────────────────────────────────────────────────────┘

You › /exit
Conversation ended. Bye!
```

Final session: TBD

---

## 9. Tech stack and dependencies

### 9.1 Existing stack (pre-filled)

Python ≥ 3.13 · uv with the `uv_build` backend · `rich` (terminal UI) · `pydantic` (config) · `anthropic`, `groq`, `ollama` (chat SDKs) · `httpx` · `youtube-transcript-api` · `pytest` (dev).

### 9.2 New dependencies

| Package | Version constraint | Purpose | Why this one | License | Alternatives rejected |
|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD | TBD |

### 9.3 System requirements

| Requirement | Needed? | How ytchat detects it | Install instructions shown to the user |
|---|---|---|---|
| ffmpeg | TBD (D12) | TBD | Windows: TBD · macOS: TBD · Linux: TBD |
| Browser for cookies | TBD (D5) | TBD | TBD |

---

## 10. Architecture and design

### 10.1 Files

| File | Action | Responsibility |
|---|---|---|
| `src/video_summarisation_project/TBD.py` | Add | TBD |
| `src/video_summarisation_project/cli.py` | Change | Routing (§8.2), pipeline wiring (§8.3), texts (§6.2) |
| `src/video_summarisation_project/config.py` | TBD | New settings (§11) |
| `src/video_summarisation_project/prompts/` | TBD | §8.5, D8 |
| `src/video_summarisation_project/transcript.py` | TBD | <!-- untouched if D7 = add alongside --> |
| `src/video_summarisation_project/vendors.py` | TBD | <!-- does the STT call live here, or in its own module? --> |
| `tests/TBD.py` | Add | §15 |
| `tests/conftest.py` | TBD | <!-- add any new env vars to the cleared list --> |
| `README.md`, `startupGuide.md`, `CLAUDE.md` | Change | §18 |

### 10.2 Interfaces

Write the exact names, signatures and contracts. Claude Code will implement these.

Example (replace or edit):

```python
def extract_reel_shortcode(link: str) -> str | None:
    """Shortcode from an Instagram Reel link, or None. Never raises, no network."""

@dataclass(frozen=True)
class ReelInfo:
    shortcode: str
    duration_seconds: float | None
    caption: str | None            # only if D4 = yes

def fetch_reel_info(shortcode: str, config: Config) -> ReelInfo:
    """Metadata only, no media download. Raises AppError (E2–E6, E10, E12, E14)."""

def download_reel_audio(shortcode: str, dest_dir: Path, config: Config) -> Path:
    """Download the audio into dest_dir and return the file path. Raises AppError."""

def transcribe(audio_path: Path, config: Config) -> str:
    """Transcript text. Raises AppError (E9, E11, E13)."""

def fetch_reel_transcript(shortcode: str, config: Config) -> str:
    """P4–P7 in one call. cli.py calls this; tests monkeypatch it."""
```

Final interfaces: TBD

- **IF-1:** Only `AppError` may leave these functions. Library exceptions are translated where they happen, following the pattern in `transcript.py` and `vendors.py`.
- **IF-2:** `cli.py` calls one function for the whole reel-to-transcript step, so `test_cli.py` can monkeypatch it the same way it patches `cli.fetch_transcript` today.
- **IF-3:** TBD

### 10.3 Data model changes

- `Conversation.video_id: str` becomes: TBD <!-- keep it and store the shortcode, or replace it with a Source (D7) -->
- `Turn`, `Reply`, `Backend`: no change expected. Exceptions: TBD
- `Config`: see §11.

### 10.4 Flow

Adjust to match your decisions:

```text
link ─▶ parse (YouTube? Instagram?) ─▶ chat backend check ─▶ STT pre-flight
     ─▶ reel info ─▶ download audio (temp folder) ─▶ transcribe ─▶ delete temp folder
     ─▶ system prompt ─▶ summary turn ─▶ Q&A loop (unchanged)
```

Final flow: TBD

### 10.5 Temporary files

- **Location:** TBD <!-- e.g. tempfile.TemporaryDirectory(prefix="ytchat-") -->
- **Clean-up:** MUST be deleted after success, after an `AppError`, and after Ctrl+C (use a context manager).
- **Max disk use:** TBD

---

## 11. Configuration

| Field in `config.json` | Type | Default | Validation | Meaning |
|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD |

<!-- Examples: transcription_provider: Literal[...] = "groq"; transcription_model: str = "..."; instagram_cookies_from_browser: str | None = None; max_reel_seconds: int = 180 -->

- **CFG-1 (pre-filled):** A `config.json` saved by the current version, without the new fields, MUST still load, with defaults filled in.
- **CFG-2 (pre-filled):** New fields are written the next time any setting is saved.
- **CFG-3:** New environment variables: TBD
- **CFG-4:** How each new field is changed (config file only, or a slash command): TBD
- **CFG-5:** What `/config` shows for the new fields: TBD

---

## 12. Error catalogue

<!-- One row per failure. Write problem and fix texts exactly as they should appear. `kind` sets the panel title (see §6.1 step 4). For style, copy _TRANSCRIPT_ERRORS in transcript.py: a plain statement of what went wrong, then what to do. -->

| ID | Trigger | kind | Problem text | Fix text |
|---|---|---|---|---|
| E1 | Not a YouTube or Instagram Reel link | input | TBD | TBD |
| E2 | Reel is private, deleted, or the link is wrong | input | TBD | TBD |
| E3 | Instagram requires login for this reel | TBD | TBD | TBD |
| E4 | Instagram rate-limits or blocks the request | TBD | TBD | TBD |
| E5 | Reel is age-restricted or region-locked | input | TBD | TBD |
| E6 | Link is an image post or carousel, not a video | input | TBD | TBD |
| E7 | ffmpeg or the download library is missing | config | TBD | TBD |
| E8 | No key for the STT provider | config | TBD | TBD |
| E9 | The STT provider rejects the key | auth | TBD | TBD |
| E10 | Reel is longer than the max duration (D6) | limit | TBD | TBD |
| E11 | No speech in the reel (D9) | input | TBD | TBD |
| E12 | Network error or timeout reaching Instagram | network | TBD | TBD |
| E13 | STT rate limit, file too large, timeout, or server error | TBD | TBD | TBD |
| E14 | Instagram changed its site and the download library can't read it | other | TBD | TBD <!-- e.g. tell the user to update ytchat to get a newer download library --> |
| E15 | TBD | TBD | TBD | TBD |

- **ERR-1:** A failure in P1–P9 leaves the previous state as it was: an open conversation stays open (§6.1 step 2.8).
- **ERR-2:** Each row above has a test that checks its `kind` and text (AC-3).

---

## 13. Non-functional requirements

| ID | Area | Requirement |
|---|---|---|
| NFR-1 | Speed | A 60-second public reel goes from Enter to summary in ≤ TBD seconds on TBD connection. |
| NFR-2 | Cost | Expected STT cost per reel: TBD. Free-tier limits that apply: TBD. |
| NFR-3 | Platforms | Windows (PowerShell), macOS and Linux, as today. |
| NFR-4 | Install | `uv tool install .` remains the only install step: TBD (depends on D12). |
| NFR-5 | Retries | TBD <!-- none, like today? --> |
| NFR-6 | Files | Nothing is written outside the config folder and the temp folder (§10.5). |
| NFR-7 | Offline | With no network, ytchat still starts. Pasting a reel link shows E12 (or the existing chat-vendor network error from P2). |
| NFR-8 | TBD | TBD |

---

## 14. Security, privacy and compliance

- **SEC-1:** Instagram cookies (D5) MUST NOT be printed, logged, or written into `config.json`. Only TBD is stored. <!-- e.g. the browser name or the cookies file path -->
- **SEC-2 (pre-filled):** API keys follow the existing rules: displayed masked (`mask_key`), saved only after the vendor accepts them.
- **SEC-3:** Temp media is deleted as described in §10.5.
- **SEC-4:** Data leaving the machine: the audio goes to TBD (the STT provider); the transcript and questions go to the chat vendor (as today). README MUST say this.
- **SEC-5:** Terms of service: TBD <!-- Instagram's terms restrict automated access and downloading. Record your intended use (e.g. personal use, public reels only) and anything that limits the feature because of it. -->
- **SEC-6:** TBD

---

## 15. Testing plan

### 15.1 Rules (pre-filled)

- Tests need no network, keys, Instagram account, or ffmpeg.
- `tests/conftest.py` already isolates the config folder and clears `GROQ_API_KEY`, `ANTHROPIC_API_KEY` and `OLLAMA_HOST`. Add any new environment variables to that list.
- The download library and STT client are faked at the module boundary. CLI tests patch one function (IF-2), the way the `fake_vendor` fixture patches `cli.fetch_transcript`.
- HTTP request shapes (e.g. the STT call) are checked with a mocked transport, the way `test_anthropic.py` does.

### 15.2 Unit tests

| Test | Module under test | Covers |
|---|---|---|
| Link parsing | TBD | Every row of the §8.1 table |
| Error translation | TBD | Each library exception → its E-id, with the right `kind` and text |
| Limits | TBD | E10, E13 |
| Temp clean-up | TBD | Temp folder gone after success, `AppError`, and `KeyboardInterrupt` |
| Transcript clean-up | TBD | FR-14 |
| Config compatibility | `test_config.py` | CFG-1 |
| STT request shape | TBD | Model, language hint and file sent as decided |
| TBD | TBD | TBD |

### 15.3 CLI tests (scripted input, in the style of `test_cli.py`)

| Test | Input lines | Output must contain |
|---|---|---|
| Full reel conversation | reel link, a question, `/exit` | the T6 panel title; `answer 3: <question>` |
| Reel link while a YouTube video is open | YouTube link, reel link, a question | the reel's summary; the answer uses the reel transcript |
| Setup problem stops before download | reel link, with no chat key saved | `Setup problem`; the reel fetch function is never called |
| Missing STT key | TBD | E8 texts |
| Failed reel keeps the previous conversation | YouTube link, broken reel link, a question | the error panel; the answer uses the YouTube transcript |
| Ctrl+C during transcription | TBD | `Cancelled.`; no conversation opened |
| TBD | TBD | TBD |

### 15.4 Manual checklist (real network, before release)

| Case | Reel URL | Expected |
|---|---|---|
| Public reel with clear speech | TBD | summary and answers |
| Music-only reel | TBD | D9 behaviour |
| Non-English reel | TBD | D10 behaviour |
| Private or deleted reel | TBD | E2 |
| Reel longer than the limit | TBD | E10 |
| Image post | TBD | E6 |
| Link with `?igsh=` in PowerShell, quoted, as a command-line argument | TBD | opens normally |
| Switch vendor mid-conversation | TBD | history kept, next answer from the new vendor |

### 15.5 Existing tests allowed to change

TBD

<!-- Default: none. If §6.2 changes T4, T6, T9 or T13, or §8.5 drops "## Transcript\n", list the affected tests named in §6.2 here, with the new expected text. -->

---

## 16. Acceptance criteria

<!-- Pass/fail checks. The work is done when all are true. -->

- [ ] **AC-1:** `uv run pytest` passes with no network.
- [ ] **AC-2:** Every row of the §8.1 table is a passing test case.
- [ ] **AC-3:** Every error E1–E15 has a test that asserts its `kind` and texts.
- [ ] **AC-4:** The §8.7 session is reproduced by a test with a faked transcript.
- [ ] **AC-5:** All existing tests pass unchanged, except those listed in §15.5.
- [ ] **AC-6:** On a clean machine with only the §9.3 requirements, `uv tool install --reinstall .` then `ytchat --version` works.
- [ ] **AC-7:** No temp files remain after success, error, or Ctrl+C.
- [ ] **AC-8:** Every row of the §15.4 manual checklist passes.
- [ ] **AC-9:** Docs are updated as listed in §18.
- [ ] **AC-10:** TBD

---

## 17. Implementation plan

| # | Milestone | Done when |
|---|---|---|
| M1 | Link parsing | §8.1 table tests pass |
| M2 | Reel info and download behind the §10.2 interface, with error translation | Tests for E2–E7, E10, E12 and E14 pass |
| M3 | Transcription, with error translation | Tests for E8, E9, E11 and E13 pass |
| M4 | CLI wiring: routing, pipeline, texts | §15.3 tests pass |
| M5 | Config and commands | §11 and §8.6 tests pass |
| M6 | Docs | §18 done |
| M7 | Manual checklist (done by you) | §15.4 passes |

**Stop for review after each milestone:** TBD <!-- yes / no -->

---

## 18. Documentation updates

| Doc | Sections | Change |
|---|---|---|
| `README.md` | Intro, vendor table, Quick start, "When something's wrong", Settings, How it works | TBD |
| `startupGuide.md` | TBD | TBD |
| `CLAUDE.md` | Architecture, Tests | TBD |
| `pyproject.toml` | `description` (T14) | TBD |

---

## 19. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Instagram changes its site and downloads break | High | Feature stops working until the download library is updated | TBD <!-- e.g. a minimum library version, and E14 telling the user how to update --> |
| Instagram blocks anonymous requests | TBD | TBD | TBD (D5) |
| STT cost or free-tier limits | TBD | TBD | TBD |
| STT invents text on music or silence | Medium | Misleading summary | D9 threshold |
| Terms of service | TBD | TBD | TBD (SEC-5) |
| TBD | TBD | TBD | TBD |

---

## 20. Open questions

| # | Question | Owner | Answer |
|---|---|---|---|
| Q1 | TBD | TBD | TBD |

---

## 21. Future work (out of scope now)

- TBD <!-- e.g. TikTok through the same source layer, transcript caching, timestamps in answers -->

---

## 22. Glossary

| Term | Meaning |
|---|---|
| Reel | A short video on Instagram, with a URL like `instagram.com/reel/<shortcode>/`. |
| Shortcode | The ID in a reel or post URL. |
| STT | Speech-to-text: turning audio into a transcript. |
| Chat vendor | The LLM provider ytchat chats with: `groq`, `anthropic` or `ollama`. |
| Backend | ytchat's wrapper around one chat vendor's SDK (`vendors.Backend`). |
| Pre-flight | The checks before any download (P2–P3). |

---

## Appendix A. Spec change log

| Version | Date | Change |
|---|---|---|
| 0.1 | TBD | First draft |
