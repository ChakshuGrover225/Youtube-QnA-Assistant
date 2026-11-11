"""YouTube video summarisation pipeline.

Flow: YouTube link -> video ID -> transcript (youtube-transcript-api)
      -> summary (Groq via langchain-groq) -> pretty print (rich)
      -> chat about the video, using the transcript as context, until /exit.

Configuration lives in settings.py, prompts in prompt_library/, and the Groq
API key in the project's .env file (GROQ_API_KEY=...).

Usage:
    uv run python src/logic/summarisation_pipeline.py "<youtube link>"
"""

import re
import sys
from urllib.parse import parse_qs, urlparse

from groq import APIError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    YouTubeTranscriptApi,
)

from settings import settings

console = Console()

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"}
_PATH_ID_PREFIXES = {"shorts", "embed", "live", "v"}


def extract_video_id(youtube_link: str) -> str | None:
    """Return the 11-character video ID from a YouTube link, or None if it isn't one."""
    link = youtube_link.strip()
    if not link:
        return None
    if "://" not in link:
        link = "https://" + link

    parsed = urlparse(link)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]

    if host == "youtu.be":
        candidate = path_parts[0] if path_parts else ""
    elif host in _YOUTUBE_HOSTS:
        if parsed.path.rstrip("/") == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif len(path_parts) >= 2 and path_parts[0] in _PATH_ID_PREFIXES:
            candidate = path_parts[1]
        else:
            candidate = ""
    else:
        return None

    return candidate if _VIDEO_ID_RE.match(candidate) else None


def fetch_transcript(video_id: str) -> str:
    """Return the video's transcript as plain text.

    Raises CouldNotRetrieveTranscript if the video doesn't exist, is unavailable,
    or has no transcript.
    """
    transcripts = YouTubeTranscriptApi().list(video_id)
    try:
        transcript = transcripts.find_transcript(settings.transcript_languages)
    except NoTranscriptFound:
        # None in the preferred languages - fall back to whatever exists.
        transcript = next(iter(transcripts), None)
        if transcript is None:
            raise

    fetched = transcript.fetch()
    return " ".join(snippet.text.replace("\n", " ") for snippet in fetched).strip()


def load_system_prompt(prompt_file: str) -> str:
    """Read a prompt from the prompt library and add settings.additional_prompt to it."""
    path = settings.prompt_dir / prompt_file
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Prompt file is empty: {path}")

    additional = settings.additional_prompt.strip()
    if additional:
        prompt += f"\n\n## Additional instructions\n{additional}"
    return prompt


def _get_llm() -> ChatGroq:
    if settings.groq_api_key is None:
        raise ValueError(
            "No Groq API key found. Add GROQ_API_KEY=... to the .env file in the "
            "project root, or set it as an environment variable."
        )
    return ChatGroq(
        model=settings.model,
        api_key=settings.groq_api_key,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        reasoning_effort=settings.reasoning_effort,
    )


def _ask(llm: ChatGroq, messages: list[BaseMessage]) -> str:
    return str(llm.invoke(messages).text).strip()


def summarise_transcript(transcript: str) -> str:
    """Summarise a transcript with Groq using the summary prompt from the prompt library."""
    system_prompt = load_system_prompt(settings.summary_prompt_file)
    return _ask(_get_llm(), [SystemMessage(content=system_prompt), HumanMessage(content=transcript)])


def load_transcript(youtube_link: str) -> tuple[str, str] | None:
    """Return (video_id, transcript) for a YouTube link.

    Prints the reason and returns None if the link is invalid, the video doesn't
    exist, or it has no transcript.
    """
    video_id = extract_video_id(youtube_link)
    if video_id is None:
        console.print(f"[bold red]Error:[/] not a valid YouTube link: {escape(youtube_link)}")
        return None

    with console.status(f"Fetching transcript for [cyan]{video_id}[/]..."):
        try:
            transcript = fetch_transcript(video_id)
        except CouldNotRetrieveTranscript as exc:
            console.print(
                f"[bold red]Error:[/] could not get a transcript for [cyan]{video_id}[/] "
                f"([yellow]{type(exc).__name__}[/])"
            )
            return None

    if not transcript:
        console.print(f"[bold red]Error:[/] transcript for [cyan]{video_id}[/] is empty")
        return None

    console.print(f"[green]Transcript fetched[/] [dim]({len(transcript.split()):,} words)[/]")
    return video_id, transcript


def _print_summary(video_id: str, summary: str) -> None:
    console.print(
        Panel(
            Markdown(summary),
            title=f"[bold]Video Summary[/] [dim]· {video_id}[/]",
            subtitle=f"[dim]{settings.model}[/]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def derive_summary(youtube_link: str) -> str:
    """Summarise a YouTube video and print it with rich.

    Returns the summary, or "" if the link is invalid, the video doesn't exist,
    or it has no transcript.
    """
    loaded = load_transcript(youtube_link)
    if loaded is None:
        return ""
    video_id, transcript = loaded

    with console.status(f"Summarising with [magenta]{settings.model}[/]..."):
        summary = summarise_transcript(transcript)

    _print_summary(video_id, summary)
    return summary


def chat_with_video(youtube_link: str) -> None:
    """Summarise a YouTube video, then answer questions about it until /exit.

    The transcript is the model's context for every answer, and the conversation
    history is kept so follow-up questions work.
    """
    loaded = load_transcript(youtube_link)
    if loaded is None:
        return
    video_id, transcript = loaded

    llm = _get_llm()
    chat_prompt = load_system_prompt(settings.chat_prompt_file)
    with console.status(f"Summarising with [magenta]{settings.model}[/]..."):
        summary = summarise_transcript(transcript)
    _print_summary(video_id, summary)

    # Seed the history with the summary so questions like "expand on point 2" work.
    messages: list[BaseMessage] = [
        SystemMessage(content=f"{chat_prompt}\n\n## Transcript\n{transcript}"),
        HumanMessage(content="Summarise this video."),
        AIMessage(content=summary),
    ]

    exit_command = settings.exit_command
    console.rule(f"[bold]Ask about the video[/] [dim]· type {escape(exit_command)} to quit[/]")
    try:
        while True:
            question = console.input("\n[bold green]You ›[/] ").strip()
            if not question:
                continue
            if question.lower() == exit_command.lower():
                break

            messages.append(HumanMessage(content=question))
            try:
                with console.status("Thinking..."):
                    answer = _ask(llm, messages)
            except APIError as exc:
                messages.pop()  # drop the unanswered question so history stays consistent
                console.print(f"[bold red]Groq error:[/] {escape(str(exc))}")
                continue

            messages.append(AIMessage(content=answer))
            console.print(
                Panel(Markdown(answer), title="[bold]Assistant[/]", title_align="left",
                      border_style="magenta", padding=(0, 1))
            )
    except (KeyboardInterrupt, EOFError):
        console.print()

    console.print("[dim]Conversation ended.[/]")


if __name__ == "__main__":
    link = sys.argv[1] if len(sys.argv) > 1 else console.input("[bold]YouTube link:[/] ")
    chat_with_video(link)


'''
Okay, this looks good, but now I want to improve this. 

Now, what I want to do is run it like a conversation. 
In that, I want the transcript of this video to be used as my context, and the conversation happens on it, And the question that I ask should be answered based on the transcript. 
Let's say, if I want to ask a further question, I can also ask it. 
When I specifically write `/exit`, the conversation should end. 



'''