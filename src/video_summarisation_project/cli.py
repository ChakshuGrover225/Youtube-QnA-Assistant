"""ytchat: chat with any YouTube video from your terminal.

Paste a YouTube link, get a summary, then ask questions answered from the
video's transcript. Slash commands switch the LLM vendor, model and API key;
every change is saved, so it sticks the next time you run ytchat.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources import files

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .config import VENDOR_INFO, VENDORS, Config, api_key_for, config_path, load_config, mask_key, save_config, vendor_for_key
from .errors import AppError
from .transcript import extract_video_id, fetch_transcript
from . import vendors
from .vendors import Backend, Reply, Turn, guess_vendor, normalize_model_name

# name -> (usage, description)
COMMANDS: dict[str, tuple[str, str]] = {
    "/help": ("/help", "Show this list"),
    "/add-api-key": ("/add-api-key [vendor]", "Save your API key for the current vendor (or the one you name)"),
    "/change-model": ("/change-model [name]", "Pick the model, e.g. opus 5.5 · openai/gpt-oss-120b · qwen3:0.6b"),
    "/change-vendor": ("/change-vendor [name]", "Switch the LLM vendor: anthropic, groq or ollama"),
    "/models": ("/models", "List the models the current vendor offers"),
    "/config": ("/config", "Show your settings and where they're saved"),
    "/new": ("/new", "Drop the current video and open another one"),
    "/exit": ("/exit", "End the conversation and quit"),
}

_ERROR_TITLES = {
    "auth": "API key problem",
    "model": "Model problem",
    "config": "Setup problem",
    "network": "Connection problem",
    "limit": "Limit reached",
    "input": "Can't do that",
    "other": "Something went wrong",
}


def _clean(text: str) -> str:
    # PowerShell adds a byte-order mark when piping text into a program.
    return text.replace("﻿", "").strip()


def _prompt_text(name: str) -> str:
    return (files(__package__) / "prompts" / name).read_text(encoding="utf-8").strip()


def print_error(console: Console, exc: AppError) -> None:
    body = f"[bold]{escape(exc.problem)}[/]"
    if exc.fix:
        body += f"\n[yellow]→ {escape(exc.fix)}[/]"
    console.print(Panel(body, title=f"[bold red]{_ERROR_TITLES.get(exc.kind, 'Error')}[/]", title_align="left", border_style="red", padding=(0, 1)))


@dataclass
class Conversation:
    video_id: str
    system: str
    turns: list[Turn] = field(default_factory=list)


class App:
    def __init__(self, console: Console, config: Config) -> None:
        self.console = console
        self.config = config
        self._backend: Backend | None = None  # built and checked lazily; reset by every settings change
        self.conversation: Conversation | None = None
        self._commands: dict[str, Callable[[str], None]] = {
            "/help": self.cmd_help,
            "/add-api-key": self.cmd_add_api_key,
            "/change-model": self.cmd_change_model,
            "/change-vendor": self.cmd_change_vendor,
            "/models": self.cmd_models,
            "/config": self.cmd_config,
            "/new": self.cmd_new,
        }

    # --- Main loop --------------------------------------------------------

    def run(self, link: str | None = None) -> int:
        self._banner()
        if link:
            self.open_video(link)
        while True:
            prompt = "[bold green]You ›[/] " if self.conversation else "[bold cyan]YouTube link ›[/] "
            try:
                line = _clean(self.console.input("\n" + prompt))
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                break
            if not line:
                continue
            if line.startswith("/"):
                if not self.handle_command(line):
                    break
            elif self.conversation is None or extract_video_id(line):
                self.open_video(line)
            else:
                self.ask(line)
        self.console.print("[dim]Conversation ended. Bye![/]")
        return 0

    def handle_command(self, line: str) -> bool:
        """Run a slash command. Returns False when the app should exit."""
        name, _, arg = line.partition(" ")
        name = name.lower()
        if name in ("/exit", "/quit"):
            return False
        handler = self._commands.get(name)
        try:
            if handler is None:
                raise AppError(f"Unknown command '{name}'.", "Type /help to see the commands.", kind="input")
            handler(arg.strip())
        except AppError as exc:
            self.show_error(exc)
        return True

    # --- Conversation -----------------------------------------------------

    def backend(self) -> Backend:
        """The backend for the saved vendor + model, checked once after each settings change."""
        if self._backend is None:
            backend = vendors.make_backend(self.config)
            with self.console.status(f"Checking {backend.label} · {escape(backend.model)}..."):
                backend.check()
            self._backend = backend
        return self._backend

    def open_video(self, link: str) -> None:
        try:
            video_id = extract_video_id(link)
            if video_id is None:
                raise AppError(
                    f"That's not a YouTube video link: {link}",
                    "Paste a link like https://www.youtube.com/watch?v=VIDEO_ID or https://youtu.be/VIDEO_ID. "
                    "Type /help for commands.",
                    kind="input",
                )
            backend = self.backend()  # catch setup problems before downloading anything
            with self.console.status(f"Fetching the transcript for [cyan]{video_id}[/]..."):
                transcript = fetch_transcript(video_id, self.config.transcript_languages)
            self.console.print(f"[green]✓[/] Transcript fetched [dim]({len(transcript.split()):,} words)[/]")

            conversation = Conversation(video_id, self._system_prompt(transcript))
            reply = self._complete(
                conversation, _prompt_text("summary_request.md"), f"Summarising with [magenta]{escape(backend.model)}[/]..."
            )
        except AppError as exc:
            self.show_error(exc)
            return
        except KeyboardInterrupt:
            self.console.print("[dim]Cancelled.[/]")
            return

        self.conversation = conversation
        self._show_reply(reply, title=f"[bold]Video summary[/] [dim]· {video_id}[/]", border="cyan", padding=(1, 2))
        self.console.rule("[bold]Ask anything about the video[/] [dim]· /help for commands · /exit to quit[/]")

    def ask(self, question: str) -> None:
        assert self.conversation is not None
        try:
            reply = self._complete(self.conversation, question, "Thinking...")
        except AppError as exc:
            self.show_error(exc)
            return
        except KeyboardInterrupt:
            self.console.print("[dim]Cancelled.[/]")
            return
        self._show_reply(reply, title="[bold]Assistant[/]", border="magenta", padding=(0, 1))

    def _complete(self, conversation: Conversation, message: str, status: str) -> Reply:
        """Send `message`, add the exchange to the history, and return the reply."""
        backend = self.backend()
        conversation.turns.append(Turn("user", message))
        try:
            with self.console.status(status):
                reply = backend.chat(conversation.system, conversation.turns)
            if not reply.text:
                raise AppError(
                    f"{backend.model} returned an empty answer." + (f" {reply.note}" if reply.note else ""),
                    "Ask again, or try another model with /change-model.",
                )
        except BaseException:
            conversation.turns.pop()  # drop the unanswered message so the history stays consistent
            raise
        conversation.turns.append(Turn("assistant", reply.text, raw=reply.raw, raw_vendor=backend.vendor))
        return reply

    def _system_prompt(self, transcript: str) -> str:
        prompt = _prompt_text("chat_system.md")
        if extra := self.config.additional_prompt.strip():
            prompt += f"\n\n## Additional instructions\n{extra}"
        return f"{prompt}\n\n## Transcript\n{transcript}"

    # --- Commands ---------------------------------------------------------

    def cmd_help(self, _arg: str) -> None:
        table = Table(show_header=False, box=None, padding=(0, 2))
        for usage, description in COMMANDS.values():
            table.add_row(f"[bold cyan]{escape(usage)}[/]", description)
        self.console.print(Panel(table, title="[bold]Commands[/]", title_align="left", border_style="cyan"))
        self.console.print("[dim]Anything else you type is a question about the current video, or a YouTube link to open.[/]")

    def cmd_config(self, _arg: str) -> None:
        table = Table(box=None, padding=(0, 2), header_style="bold")
        for column in ("", "Vendor", "Model", "API key"):
            table.add_column(column)
        for vendor in VENDORS:
            info, settings = VENDOR_INFO[vendor], self.config.settings_for(vendor)
            if info.needs_key:
                key, source = api_key_for(self.config, vendor)
                key_text = f"{mask_key(key)} [dim]({'saved' if source == 'saved' else 'from ' + source})[/]" if key else "[red]not set[/]"
            else:
                key_text = f"[dim]not needed · {escape(settings.host or 'localhost:11434')}[/]"
            active = "[bold green]●[/]" if vendor == self.config.vendor else ""
            table.add_row(active, info.label, escape(settings.model), key_text)
        self.console.print(table)
        max_tokens = self.config.max_tokens or "vendor default"
        self.console.print(
            f"[dim]● = in use · temperature {self.config.temperature} (Groq/Ollama) · max tokens {max_tokens} · "
            f"transcript languages {', '.join(self.config.transcript_languages)}[/]"
        )
        self.console.print(f"[dim]Saved in {escape(str(config_path()))}[/]")

    def cmd_models(self, _arg: str) -> None:
        backend = vendors.make_backend(self.config)
        with self.console.status(f"Asking {backend.label} for its models..."):
            models = sorted(backend.list_models(), key=lambda m: m.id.lower())
        if not models:
            self.console.print("No models installed yet. Download one with [bold]ollama pull qwen3:0.6b[/], then try again.")
            return
        current = self.config.settings_for().model.lower()
        table = Table(box=None, padding=(0, 2), header_style="bold")
        table.add_column("")
        table.add_column(f"{backend.label} models")
        table.add_column("", style="dim")
        for m in models:
            table.add_row("[bold green]●[/]" if m.id.lower() == current else "", escape(m.id), escape(m.note))
        self.console.print(table)
        self.console.print("[dim]Switch with /change-model <name>[/]")

    def cmd_change_vendor(self, arg: str) -> None:
        if not arg:
            for i, vendor in enumerate(VENDORS, 1):
                marker = " [green](current)[/]" if vendor == self.config.vendor else ""
                self.console.print(f"  [bold]{i}[/]. {vendor}{marker}")
            arg = self._ask("Vendor (name or number)")
            if not arg:
                self.console.print("[dim]Vendor not changed.[/]")
                return
        choice = arg.strip().lower()
        if choice.isdigit() and 1 <= int(choice) <= len(VENDORS):
            choice = VENDORS[int(choice) - 1]
        if choice not in VENDORS:
            raise AppError(
                f"'{arg}' isn't a supported vendor.",
                f"Choose one of: {', '.join(VENDORS)} - e.g. /change-vendor groq",
                kind="input",
            )

        info = VENDOR_INFO[choice]
        if choice == self.config.vendor:
            self.console.print(f"Already using {info.label}.")
        else:
            self.config.vendor = choice
            self._save()
            self.console.print(f"[green]✓[/] Vendor set to [bold]{info.label}[/] · model {escape(self.config.settings_for().model)} [dim](saved)[/]")

        if info.needs_key and not api_key_for(self.config, choice)[0]:
            self.console.print(f"No {info.label} API key saved yet [dim](create one at {info.key_url})[/].")
            key = self._ask_secret(f"Paste your {info.label} API key (hidden), or press Enter to skip")
            if not key:
                self.console.print("[dim]Skipped. Add it later with /add-api-key.[/]")
                return
            if not self._store_key(choice, key):
                return
        self._verify()

    def cmd_add_api_key(self, arg: str) -> None:
        vendor, key = self.config.vendor, ""
        if arg:
            if arg.lower() in VENDORS:
                vendor = arg.lower()
            else:
                key = arg
        info = VENDOR_INFO[vendor]
        if not info.needs_key:
            self.console.print(
                f"{info.label} runs on your computer and doesn't need an API key. "
                "[dim]To add a key for another vendor: /add-api-key groq or /add-api-key anthropic[/]"
            )
            return
        if not key:
            key = self._ask_secret(f"Paste your {info.label} API key (input hidden, Enter to cancel)")
            if not key:
                self.console.print("[dim]Cancelled - no key saved.[/]")
                return
        if self._store_key(vendor, key) and vendor == self.config.vendor:
            self._verify()

    def cmd_change_model(self, arg: str) -> None:
        vendor = self.config.vendor
        info, settings = VENDOR_INFO[vendor], self.config.settings_for()
        if not arg:
            arg = self._ask(f"Model for {info.label} (current: {settings.model} · /models lists them)")
            if not arg:
                self.console.print("[dim]Model not changed.[/]")
                return
        requested = normalize_model_name(vendor, arg)

        verified: Backend | None = None
        try:
            candidate = vendors.make_backend(self.config, model=requested)
            with self.console.status(f"Checking '{escape(requested)}' with {info.label}..."):
                candidate.check()
            verified = candidate
        except AppError as exc:
            guessed = guess_vendor(requested)
            if exc.kind != "model" and guessed and guessed != vendor:
                exc = AppError(
                    f"'{arg}' looks like {VENDOR_INFO[guessed].a_label} model, but you're using {info.label}.",
                    f"Switch first with /change-vendor {guessed}, then run /change-model {arg} again.",
                    kind="model",
                )
            if exc.kind == "model":
                self.show_error(exc)
                self.console.print("[dim]Model not changed.[/]")
                return
            # The vendor couldn't be asked (no key yet, offline, Ollama not running...).
            # Save anyway - it's checked again before the next chat.
            self.console.print(f"[yellow]![/] Couldn't check the model with {info.label}: {escape(exc.problem)}")
            if exc.fix:
                self.console.print(f"  [yellow]→ {escape(exc.fix)}[/]")

        resolved = verified.model if verified else requested
        settings.model = resolved
        self._save()
        self._backend = verified
        shown = f" [dim]('{escape(arg)}' → {escape(resolved)})[/]" if resolved != arg else ""
        status = "[dim](saved)[/]" if verified else "[dim](saved, not verified yet - it's checked before your next chat)[/]"
        self.console.print(f"[green]✓[/] Model set to [bold]{escape(resolved)}[/] for {info.label}{shown} {status}")

    def cmd_new(self, _arg: str) -> None:
        if self.conversation is None:
            self.console.print("No video is open. Paste a YouTube link to start.")
            return
        self.conversation = None
        self.console.print("[dim]Closed the video. Paste another YouTube link.[/]")

    # --- Helpers ----------------------------------------------------------

    def _store_key(self, vendor: str, key: str) -> bool:
        """Check a key with the vendor and save it. Keys the vendor rejects are not saved."""
        key = key.strip().strip("'\"")
        info = VENDOR_INFO[vendor]
        owner = vendor_for_key(key)
        if owner and owner != vendor:
            self.show_error(AppError(
                f"That looks like {VENDOR_INFO[owner].a_label} key, not {info.a_label} key.",
                f"Save it with /add-api-key {owner}, or paste your {info.label} key (it starts with '{info.key_prefix}').",
                kind="auth",
            ))
            self.console.print("[dim]Key not saved.[/]")
            return False

        verified = True
        try:
            with self.console.status(f"Checking the key with {info.label}..."):
                vendors.make_backend(self.config, vendor, api_key=key).list_models()
        except AppError as exc:
            if exc.kind == "auth":
                self.show_error(exc)
                self.console.print("[dim]Key not saved.[/]")
                return False
            verified = False
            self.console.print(f"[yellow]![/] Couldn't verify the key right now: {escape(exc.problem)}")

        self.config.settings_for(vendor).api_key = key
        self._save()
        if vendor == self.config.vendor:
            self._backend = None
        state = "verified and saved" if verified else "saved (not verified)"
        self.console.print(f"[green]✓[/] {info.label} API key {state} [dim]({mask_key(key)})[/]")
        return True

    def _verify(self) -> None:
        """Check the current vendor + model + key and say whether it's ready."""
        self._backend = None
        try:
            backend = self.backend()
        except AppError as exc:
            self.show_error(exc)
            return
        self.console.print(f"[green]✓[/] Ready: {backend.label} · {escape(backend.model)}")

    def _save(self) -> None:
        save_config(self.config)
        self._backend = None

    def _ask(self, label: str) -> str:
        try:
            return _clean(self.console.input(f"[bold]{label}:[/] "))
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            return ""

    def _ask_secret(self, label: str) -> str:
        try:
            # Hide what's typed in a terminal; read plainly when input is piped (scripts, tests).
            return _clean(self.console.input(f"[bold]{label}:[/] ", password=sys.stdin.isatty()))
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            return ""

    def show_error(self, exc: AppError) -> None:
        print_error(self.console, exc)

    def _show_reply(self, reply: Reply, title: str, border: str, padding: tuple[int, int]) -> None:
        subtitle = f"[dim]{self._backend.vendor} · {escape(self._backend.model)}[/]" if self._backend else None
        self.console.print(
            Panel(Markdown(reply.text), title=title, title_align="left", subtitle=subtitle,
                  subtitle_align="right", border_style=border, padding=padding)
        )
        if reply.note:
            self.console.print(f"[yellow]Note:[/] {escape(reply.note)}")

    def _banner(self) -> None:
        vendor = self.config.vendor
        info, settings = VENDOR_INFO[vendor], self.config.settings_for()
        if not info.needs_key:
            key_text = "[dim]runs locally[/]"
        elif api_key_for(self.config, vendor)[0]:
            key_text = "[green]API key ✓[/]"
        else:
            key_text = "[red]no API key - run /add-api-key[/]"
        self.console.print(
            Panel(
                "Chat with any YouTube video.\n"
                f"[dim]Vendor[/] {info.label} · [dim]Model[/] {escape(settings.model)} · {key_text}\n\n"
                "Paste a YouTube link to start · [cyan]/help[/] for commands · [cyan]/exit[/] to quit",
                title=f"[bold]ytchat[/] [dim]v{__version__}[/]",
                title_align="left",
                border_style="cyan",
                padding=(1, 2),
                expand=False,
            )
        )


def _use_utf8_when_piped() -> None:
    # Windows pipes default to a legacy code page that can't print the box-drawing
    # characters rich uses; real terminals are already UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _use_utf8_when_piped()
    parser = argparse.ArgumentParser(
        prog="ytchat",
        description="Chat with any YouTube video from your terminal, using Groq, Anthropic or Ollama.",
        epilog="Inside ytchat, type /help to see the commands.",
    )
    parser.add_argument("link", nargs="?", help="YouTube link to open straight away (quote it)")
    parser.add_argument("--version", action="version", version=f"ytchat {__version__}")
    args = parser.parse_args(argv)

    console = Console()
    try:
        config = load_config()
    except AppError as exc:
        print_error(console, exc)
        return 1
    return App(console, config).run(args.link)
