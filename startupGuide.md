# ytchat - Startup Guide


## What ytchat does

ytchat is a small program you run in a terminal. You give it a YouTube or Instagram Reel link and it:

1. Gets the video's transcript: a YouTube video's captions, or for a reel, it listens to the audio.
2. Shows you a short summary of the video.
3. Lets you ask questions about the video.

It uses an AI model to do this. You choose which company's AI to use, and you
use your own account with them:

| Provider | Cost | What you need |
|---|---|---|
| **Groq** (recommended to start) | Free tier | A free Groq account and API key |
| **Anthropic** (Claude) | Paid, pay-as-you-go | An Anthropic account with credits and an API key |
| **Ollama** | Free | The Ollama app on your own computer - no account or key |


## What you need

- A computer running Windows, macOS or Linux
- An internet connection
- The ytchat project folder (the folder that contains `pyproject.toml` and this guide).


## Step 1 - Open a terminal

A terminal is a window where you type commands.

| OS | what to open |
|----|--------------|
| **Windows:** | press the **Start** button, type `PowerShell`, and open **Windows PowerShell** (or **Terminal**). |
|**macOS:** | press `Cmd + Space`, type `Terminal`, and press Enter.|
|**Linux:**| open your **Terminal** app (often `Ctrl + Alt + T`).|



## Step 2 - Install uv

Pre-requisite - Make sure you have python 3.13 or bigger installed

**Windows** (in PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS or Linux:**

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

When it finishes, **close the terminal and open a new one** (so it notices uv), then check it worked:

```sh
uv --version
```

You should see something like `uv 0.12.17`. If you see "not recognized" or "command not found",
close and reopen the terminal once more, or restart your computer.

---

## Step 3 - Install ytchat

First, move the terminal into the ytchat project folder with `cd`, followed by the folder's
location in quotes. For example:

```powershell
# Windows - change the path to wherever the folder is on your computer
cd "C:\Users\YourName\Downloads\video-summarisation-project"
```

```sh
# macOS / Linux
cd "$HOME/Downloads/video-summarisation-project"
```



Now install ytchat:

```sh
uv tool install . -c constraints.txt
```
When it's done you'll see `Installed 1 executable: ytchat`.

(`-c constraints.txt` installs the exact library versions this project was tested with,
instead of whatever was published most recently.)


<br>
Check it worked:

```sh
ytchat --version
```

You should see `ytchat 0.1.0`. If you get "not recognized" or "command not found", run
`uv tool update-shell`, close the terminal, open a new one, and try again.

<h4>From now on, `ytchat` works from you computer - you don't need to `cd` into the project again.
</h4>
---

## Step 4 - Get an API key (pick one option)

### Option A - Groq (free, recommended)

1. Go to **https://console.groq.com** and sign up (Google or email).
2. Open **https://console.groq.com/keys** and click **Create API Key**.
3. Give it any name (e.g. `ytchat`) and click **Submit**.
4. **Copy the key now** - it starts with `gsk_`, and Groq only shows it once.
   If you lose it, just create a new one.

### Option B - Anthropic / Claude (paid)

1. Go to **https://platform.claude.com** and sign up.
2. Add credits to your account under **Billing** (requests fail without credits).
3. Open **https://platform.claude.com/settings/keys** and click **Create Key**.
4. Copy the key - it starts with `sk-ant-`.

### Option C - Ollama (free, runs on your own computer, no key)

1. Download and install Ollama from **https://ollama.com/download**, then open the Ollama app.
2. In your terminal, download a model:

   ```sh
   ollama pull qwen3:0.6b
   ```

   `qwen3:0.6b` is small and fast but basic. If your computer has 8 GB+ of memory,
   `ollama pull llama3.2` gives better answers.



## Step 5 - Start ytchat and add your key

Type:

```sh
ytchat
```

You'll see a welcome box like this:

```text
┌─ ytchat v0.1.0 ───────────────────────────────────────────────────────────┐
│                                                                           │
│  Chat with any YouTube video or Instagram Reel.                           │
│  Vendor Groq · Model openai/gpt-oss-120b · no API key - run /add-api-key  │
│                                                                           │
│  Paste a YouTube or Instagram link · /help for commands · /exit to quit   │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘

Video link ›
```

ytchat starts out set up for **Groq**. Now follow the part that matches the option you picked in Step 4.

**If you picked Groq (Option A):** type `/add-api-key` and press Enter, then paste your key and press Enter.

```text
Video link › /add-api-key
Paste your Groq API key (input hidden, Enter to cancel):
✓ Groq API key verified and saved (gsk_…a1b2)
✓ Ready: Groq · openai/gpt-oss-120b
```

> **Nothing appears when you paste - that's normal.** The key is hidden on purpose,
> like a password. Paste once and press Enter.

**If you picked Anthropic (Option B):** switch to it, then paste your key when asked:

```text
Video link › /change-vendor anthropic
✓ Vendor set to Anthropic · model claude-opus-5-5 (saved)
No Anthropic API key saved yet (create one at https://platform.claude.com/settings/keys).
Paste your Anthropic API key (hidden), or press Enter to skip:
✓ Anthropic API key verified and saved (sk-a…c3d4)
✓ Ready: Anthropic · claude-opus-5-5
```

**If you picked Ollama (Option C):** make sure the Ollama app is open, switch to it, then
choose the model you downloaded:

```text
Video link › /change-vendor ollama
✓ Vendor set to Ollama · model qwen3:0.6b (saved)
✓ Ready: Ollama · qwen3:0.6b
```

If you downloaded `llama3.2` instead, you'll first see a **Model problem** saying
`qwen3:0.6b` isn't installed - that's expected. Just type `/change-model llama3.2`.

You only do this step once. ytchat saves your choice and key, and remembers them every time you start it.

---

## Step 6 - Chat with your first video

1. Open a YouTube video in your browser and copy its link from the address bar.
   For a quick first test you can use this 19-second video:
   `https://www.youtube.com/watch?v=jNQXAC9IVRw`
2. Paste the link at the `Video link ›` prompt and press Enter.
3. ytchat fetches the transcript and shows a summary.
4. The prompt changes to `You ›`. Type any question about the video and press Enter.
   Ask as many follow-up questions as you like - it remembers the conversation.
5. When you're done, type `/exit`.

```text
Video link › https://www.youtube.com/watch?v=jNQXAC9IVRw
✓ Transcript fetched (39 words)
┌─ Video summary · jNQXAC9IVRw ─────────────────────────────────────┐
│  TL;DR: A quick glimpse of elephants, highlighting their trunks.  │
│   • The narrator is standing in front of elephants.               │
│   • The main focus is on the elephants' very long trunks.         │
└───────────────────────────────────────── groq · openai/gpt-oss-120b ┘
──────── Ask anything about the video · /help for commands · /exit to quit ────────

You › What does he say is cool about them?
┌─ Assistant ───────────────────────────────────────────────────────┐
│ He says the cool thing is that they have really, really long      │
│ trunks.                                                           │
└───────────────────────────────────────────────────────────────────┘

You › /exit
Conversation ended. Bye!
```

If you ask about something the video doesn't cover, ytchat says so instead of making
something up.

**That's it - you're set up.**

---

## Everyday use

Open a terminal (from any folder) and type `ytchat`. Then paste a link and chat.

You can also open a video straight away - keep the quotes around the link:

```sh
ytchat "https://www.youtube.com/watch?v=VIDEO_ID"
```

To switch to a different video, just paste a new link at the `You ›` prompt, or type `/new` first.

### Instagram Reels

Reel links work the same way - paste one like `https://www.instagram.com/reel/DflaaesxV7S/`.
Two differences from YouTube:

- **Reels need a Groq key, even if you chat with Anthropic or Ollama.** Reels have no
  captions, so ytchat sends the reel's audio to Groq to turn the speech into text. If you
  haven't added one yet, type `/add-api-key groq` and paste your Groq key (Step 4, Option A).
- **Only public reels work.** If a reel only opens when you're logged in to Instagram,
  ytchat can't open it. Reels with only music (no talking) can't be summarised either.

---

## Command cheat sheet

Type these at the `Video link ›` or `You ›` prompt. Anything that doesn't start with
`/` is treated as a question (or a YouTube or Instagram Reel link).

You don't need to remember them: type `/` and the list appears. Keep typing to narrow it
(`/s` shows only `/save-transcript`), press Tab to pick one, then Enter.

| Command | What it does |
|---|---|
| `/help` | Shows all the commands |
| `/add-api-key` | Saves your API key for the current provider. `/add-api-key anthropic` saves one for a specific provider. |
| `/change-vendor` | Switches AI provider: `anthropic`, `groq` or `ollama`. Type the name (`/change-vendor groq`), or just `/change-vendor` to pick from a list. |
| `/change-model` | Switches the AI model, e.g. `/change-model opus 5.5` or `/change-model qwen3:0.6b`. |
| `/models` | Lists the models your current provider offers. ● marks the one you're using. |
| `/config` | Shows your current settings (keys are partly hidden) and where they're saved. |
| `/save-transcript` | Saves the open video's summary and transcript to a text file, e.g. `job-search-in-norway-12-11-26.txt`. |
| `/change-files-save-path` | Picks the folder `/save-transcript` saves to, e.g. `/change-files-save-path D:\Notes\ytchat`. |
| `/new` | Closes the current video so you can open another. |
| `/exit` | Ends the conversation and closes ytchat. `Ctrl + C` also works. |

Every change you make with these commands is saved straight away.

---

## Switching provider or model

Each provider remembers its own model and key, so you can switch back and forth freely -
even in the middle of a conversation about a video.

```text
/change-vendor groq            → use Groq
/change-vendor anthropic       → use Claude
/change-vendor ollama          → use a model on your own computer

/models                        → see what models the current provider has
/change-model openai/gpt-oss-20b   → a faster Groq model
/change-model opus 5.5         → Claude Opus 5.5 (you can type friendly names)
/change-model sonnet 5.5       → Claude Sonnet 5.5 (cheaper than Opus)
/change-model llama3.2         → an Ollama model you've downloaded
```

ytchat checks the model exists before saving it. If you mistype a name, it suggests the
closest match.

---

## If something goes wrong

ytchat never just crashes with a wall of text - it shows a box with a title, what went
wrong, and what to do (the line starting with `→`). The most common ones:

| You see | What it means | What to do |
|---|---|---|
| **Setup problem** - No API key saved for Groq | You haven't added a key for this provider yet | Type `/add-api-key` and paste your key |
| **API key problem** - Groq rejected your API key | The key is wrong, deleted, or copied incompletely | Create a new key (Step 4) and run `/add-api-key` again. ytchat won't save a key the provider rejects. |
| **API key problem** - That looks like an Anthropic key, not a Groq key | You pasted a key for the other provider | Use `/add-api-key anthropic` (or switch provider first) |
| **Model problem** - Model '…' isn't available on Groq | The model name is wrong, or belongs to another provider | Run `/models`, then `/change-model <name>`. If it says the model looks like another provider's, run the `/change-vendor` it suggests. |
| **Model problem** - Model '…' isn't installed in Ollama | You haven't downloaded that model | Run `ollama pull <model name>` in a terminal, then try again |
| **Connection problem** - Can't connect to Ollama | The Ollama app isn't running | Open the Ollama app (or run `ollama serve` in another terminal) |
| **Connection problem** - Couldn't reach Groq / Anthropic | No internet, or a VPN/proxy is in the way | Check your connection and try again |
| **Limit reached** - too long / rate limit | Long videos can be too big for a model, and Groq's free tier limits how much you can send per minute | Wait a minute, try a shorter video, pick another model (`/models`), or switch provider |
| **Can't do that** - Captions are turned off for this video | ytchat needs a video with captions | Try another video (auto-generated captions are fine) |
| **Can't do that** - That's not a YouTube or Instagram Reel link | What you typed isn't a video link (or no video is open yet) | Copy the full link from your browser's address bar |
| **Setup problem** - Instagram reels are transcribed with Groq, but no Groq API key is saved | Reels need a Groq key, whichever provider you chat with | Type `/add-api-key groq` and paste your Groq key |
| **Can't do that** - Instagram didn't return this reel | The reel is private, deleted, or only visible when logged in | Try a public reel - check it opens in a private (incognito) browser window |
| **Can't do that** - There's too little speech in this reel to chat about | The reel is only music, or the talking is too short | Try another reel |
| `ytchat` is "not recognized" / "command not found" | The terminal can't find ytchat yet | Run `uv tool update-shell`, then close and reopen the terminal |

If a question fails, the conversation isn't lost - fix the problem and ask again.

---

## Good to know

- **Your key stays on your computer.** It's saved in a settings file only you can read,
  and is only sent to the provider it belongs to. Don't share that file.
  - Windows: `%APPDATA%\ytchat\config.json`
  - macOS / Linux: `~/.config/ytchat/config.json`
  - `/config` shows the exact location.
- **Costs:** Groq's free tier and Ollama cost nothing. Anthropic charges per use from your
  account credits - longer videos and more questions cost more.
- **Languages:** ytchat prefers English captions but will use any language the video has,
  and answers in English.
- **Start fresh:** to reset everything, delete the settings file above. You'll need to add
  your keys again.
- **More details** (advanced settings, how it works): see `README.md` in the project folder.

---

## Updating or removing ytchat

**Update** (after you get a newer copy of the project folder) - in a terminal, inside the project folder:

```sh
uv tool install --reinstall . -c constraints.txt
```

**Uninstall:**

```sh
uv tool uninstall video-summarisation-project
```

This removes the program. Your settings file stays, so delete it too if you want everything gone.



## Command i ran:

1. Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
2. uv sync
3. .\.venv\Scripts\activate
4. -copy and create a new .env