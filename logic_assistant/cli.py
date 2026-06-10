"""Terminal front-end: a REPL that Wispr Flow dictates into.

Auto-send: Wispr Flow types text but never presses Enter, so we read stdin in
raw (cbreak) mode and submit automatically once input goes quiet for
LOGIC_AUTOSEND_MS (default 1200 ms). Enter still submits immediately.
"""

from __future__ import annotations

import codecs
import os
import select
import sys
import termios
import tty

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from .agent import LogicAgent
from .executor import dry_run_enabled
from .registry import Registry

console = Console()


def autosend_seconds() -> float:
    try:
        return int(os.environ.get("LOGIC_AUTOSEND_MS", "1200")) / 1000.0
    except ValueError:
        return 1.2


def read_command(idle_s: float) -> str:
    """Read one command. Submits on Enter OR after idle_s of input silence
    (once there is non-whitespace content). Ctrl+C/Ctrl+D raise as usual."""
    if not sys.stdin.isatty():  # piped input / tests
        return input()

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    chars: list[str] = []

    def has_content() -> bool:
        return bool("".join(chars).strip())

    try:
        tty.setcbreak(fd)
        while True:
            timeout = idle_s if has_content() else None
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                break  # input went quiet with content → auto-send

            for ch in decoder.decode(os.read(fd, 4096)):
                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return "".join(chars)
                if ch == "\x03":
                    raise KeyboardInterrupt
                if ch == "\x04":
                    raise EOFError
                if ch in ("\x7f", "\x08"):  # backspace
                    if chars:
                        chars.pop()
                        sys.stdout.write("\b \b")
                elif ch.isprintable():
                    chars.append(ch)
                    sys.stdout.write(ch)
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)

    sys.stdout.write("\n")
    sys.stdout.flush()
    return "".join(chars)


def emit(kind: str, text: str) -> None:
    style = {"action": "cyan", "result": "dim", "error": "bold red"}.get(kind, "dim")
    prefix = {"action": "▸", "result": "·", "error": "✗"}.get(kind, "·")
    console.print(f"  [{style}]{prefix} {text}[/{style}]")


def confirm(prompt: str) -> bool:
    return Confirm.ask(f"  [yellow]{prompt}[/yellow]", default=False)


def main() -> int:
    load_dotenv()
    try:
        registry = Registry.load("commands.yaml")
    except Exception as e:
        console.print(f"[bold red]Failed to load commands.yaml:[/bold red] {e}")
        return 1

    agent = LogicAgent(registry, confirm=confirm, emit=emit)
    idle_s = autosend_seconds()

    mode = " [yellow](dry-run)[/yellow]" if dry_run_enabled() else ""
    console.print(
        Panel.fit(
            f"[bold]LogicAssistant[/bold]{mode} · [dim]{agent.backend.label}[/dim]\n"
            f"{len(registry.actions)} actions loaded · speak via Wispr Flow "
            f"(auto-sends after {idle_s:.1f}s pause) · 'quit' to exit",
            border_style="cyan",
        )
    )

    while True:
        console.print("\n[bold green]you ›[/bold green] ", end="")
        try:
            user_text = read_command(idle_s).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\nbye")
            return 0

        if not user_text:
            continue
        if user_text.lower() in ("quit", "exit", "q"):
            return 0

        # No spinner here: the confirm prompt for risky actions needs stdin,
        # which conflicts with rich's live display.
        console.print("  [dim]thinking…[/dim]")
        try:
            reply = agent.handle(user_text)
        except Exception as e:
            console.print(f"[bold red]error:[/bold red] {e}")
            continue

        if reply:
            console.print(f"[bold cyan]logic ›[/bold cyan] {reply}")


if __name__ == "__main__":
    sys.exit(main())
