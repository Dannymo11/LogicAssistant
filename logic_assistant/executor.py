"""Send Logic Pro key commands via AppleScript (System Events).

Focus contract: we activate Logic, send the keystrokes, then restore focus to
whatever app was frontmost (your terminal / HUD) so Wispr Flow dictation keeps
landing in the assistant's input.
"""

from __future__ import annotations

import os
import subprocess

from .registry import Action

LOGIC_APP = os.environ.get("LOGIC_APP_NAME", "Logic Pro")
ACTIVATE_DELAY = 0.25  # seconds for Logic to come frontmost

# Non-character keys must be sent as macOS virtual key codes.
KEY_CODES = {
    "space": 49,
    "return": 36,
    "enter": 36,
    "tab": 48,
    "escape": 53,
    "esc": 53,
    "delete": 51,
    "up": 126,
    "down": 125,
    "left": 123,
    "right": 124,
    "home": 115,
    "end": 119,
}

MODIFIERS = {
    "cmd": "command down",
    "command": "command down",
    "opt": "option down",
    "option": "option down",
    "alt": "option down",
    "shift": "shift down",
    "ctrl": "control down",
    "control": "control down",
}


class ExecutorError(RuntimeError):
    pass


def parse_combo(combo: str) -> tuple[str, list[str]]:
    """'cmd+opt+a' -> ('a', ['command down', 'option down'])."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ExecutorError(f"Empty key combo: {combo!r}")
    *mods, key = parts
    bad = [m for m in mods if m not in MODIFIERS]
    if bad:
        raise ExecutorError(f"Unknown modifier(s) {bad} in combo {combo!r}")
    return key, [MODIFIERS[m] for m in mods]


def combo_to_applescript(combo: str) -> str:
    """One key combo -> one AppleScript keystroke/key code line."""
    key, mods = parse_combo(combo)
    using = f" using {{{', '.join(mods)}}}" if mods else ""
    if key in KEY_CODES:
        return f"key code {KEY_CODES[key]}{using}"
    if len(key) != 1:
        raise ExecutorError(
            f"Unknown special key {key!r} in combo {combo!r} "
            f"(known: {sorted(KEY_CODES)})"
        )
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'keystroke "{escaped}"{using}'


def build_script(action: Action, restore_focus: bool = True) -> str:
    """Full AppleScript for an action: focus Logic, send steps, restore focus."""
    step_lines = []
    for i, combo in enumerate(action.keys):
        step_lines.append(f"        {combo_to_applescript(combo)}")
        if i < len(action.keys) - 1:
            step_lines.append(f"        delay {action.delay}")
    steps = "\n".join(step_lines)

    restore = (
        """
    try
        tell application prevApp to activate
    end try"""
        if restore_focus
        else ""
    )

    return f"""\
tell application "System Events"
    set prevApp to name of first application process whose frontmost is true
end tell
tell application "{LOGIC_APP}" to activate
delay {ACTIVATE_DELAY}
tell application "System Events"
    tell process "{LOGIC_APP}"
{steps}
    end tell
end tell
delay 0.15{restore}
"""


def dry_run_enabled() -> bool:
    return os.environ.get("LOGIC_DRY_RUN", "").strip() not in ("", "0", "false")


def execute(action: Action, restore_focus: bool = True) -> str:
    """Run an action. Returns a short human-readable result string."""
    script = build_script(action, restore_focus=restore_focus)

    if dry_run_enabled():
        return f"[dry-run] {action.id} would send:\n{script}"

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        hint = ""
        if "not allowed assistive access" in err or "1002" in err:
            hint = (
                "\nHint: grant your terminal Accessibility permission "
                "(System Settings → Privacy & Security → Accessibility)."
            )
        raise ExecutorError(f"osascript failed for '{action.id}': {err}{hint}")
    return f"executed {action.id} ({' , '.join(action.keys)})"
