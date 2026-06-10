"""UI-agnostic agent engine: text in → LLM tool use → executor → events out.

Any front-end (CLI, HUD) drives this the same way:

    agent = LogicAgent(registry, confirm=ui.confirm, emit=ui.emit)
    reply = agent.handle("mute the drums and play from the top")

`emit(kind, text)` receives progress events ("action", "result", "error").
`confirm(prompt) -> bool` is called before any risk!=low action.

Tools exposed to the model:
    run_logic_actions — keystroke actions from commands.yaml
    get_tracks        — read track names + selection via accessibility (read-only)

The LLM is pluggable (see backends.py): Claude by default, or a local
OpenAI-compatible server (Ollama / LM Studio) via LOGIC_BACKEND=ollama.
"""

from __future__ import annotations

import json
from typing import Callable

from .backends import make_backend
from .executor import execute, ExecutorError
from .registry import Registry, TOOL_NAME
from .tracks import get_tracks, TracksError

MAX_HISTORY_ENTRIES = 60  # neutral-format entries kept for context

GET_TRACKS_TOOL = "get_tracks"

GET_TRACKS_SPEC = {
    "name": GET_TRACKS_TOOL,
    "description": (
        "Read the current Logic Pro track list (read-only). Returns each "
        "track's index, name, and whether it is currently selected. Call this "
        "whenever the user refers to a track by name or you are unsure which "
        "track is selected, then move the selection with select_next_track / "
        "select_prev_track (one step per call, top of list = index 1)."
    ),
    "parameters": {"type": "object", "properties": {}},
}

SYSTEM_PROMPT = """\
You are LogicAssistant, a hands-free voice assistant controlling Logic Pro on \
the user's Mac. The user is a music producer mid-session; their words arrive \
via dictation, so expect casual phrasing and minor transcription errors.

Rules:
- Use the run_logic_actions tool to do things in Logic. Chain multiple actions \
in one call when the request implies a sequence (e.g. "loop the selection and \
play it" → set_locators_to_selection, toggle_cycle, play_stop).
- When the user names a track ("the drums", "my vocal"), first call get_tracks \
to see names and the current selection, then move to it with repeated \
select_next_track / select_prev_track (selection moves one track per action: \
moving from index 2 to index 5 means select_next_track three times), then act. \
Match names loosely — "drums" matches "Drum Bus" or "808 Drums".
- Mute/solo/cycle/metronome are toggles. Use conversation history to reason \
about current state (e.g. if you just muted, "unmute" means toggle again).
- If a request is ambiguous or impossible with the available actions, say so \
in one short sentence — do not guess with destructive actions.
- Keep spoken replies to ONE short sentence; the user is in a creative flow. \
No emoji, no preamble.
"""


class LogicAgent:
    def __init__(
        self,
        registry: Registry,
        confirm: Callable[[str], bool],
        emit: Callable[[str, str], None] = lambda kind, text: None,
        backend=None,
    ):
        self.registry = registry
        self.confirm = confirm
        self.emit = emit
        tool_specs = [registry.tool_spec(), GET_TRACKS_SPEC]
        self.backend = backend or make_backend(tool_specs, SYSTEM_PROMPT)
        self.history: list[dict] = []

    # ── public API ───────────────────────────────────────────

    def handle(self, user_text: str) -> str:
        """Process one user utterance; returns the assistant's final reply."""
        self.history.append({"role": "user", "content": user_text})
        self._trim_history()

        while True:
            msg = self.backend.chat(self.history)
            self.history.append({"role": "assistant", "msg": msg})

            if not msg.tool_calls:
                return msg.text

            for call in msg.tool_calls:
                result = self._dispatch(call.name, call.input)
                self.history.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result}
                )

    # ── internals ────────────────────────────────────────────

    def _dispatch(self, name: str, tool_input: dict) -> str:
        if name == TOOL_NAME:
            return self._run_actions(tool_input)
        if name == GET_TRACKS_TOOL:
            return self._read_tracks()
        return f"ERROR: unknown tool '{name}'"

    def _read_tracks(self) -> str:
        self.emit("action", "get_tracks — reading track list")
        try:
            tracks = get_tracks()
        except TracksError as e:
            self.emit("error", str(e))
            return f"ERROR: {e}"
        summary = ", ".join(
            f"{t.name}{' (selected)' if t.selected else ''}" for t in tracks
        )
        self.emit("result", f"{len(tracks)} tracks: {summary}")
        return json.dumps([t.to_dict() for t in tracks])

    def _run_actions(self, tool_input: dict) -> str:
        results = []
        for action_id in tool_input.get("actions", []):
            try:
                action = self.registry.get(action_id)
            except KeyError as e:
                results.append(str(e))
                continue

            if action.risk != "low":
                if not self.confirm(f"{action.desc}?"):
                    results.append(f"user declined {action_id}; stopped sequence")
                    self.emit("result", f"declined {action_id}")
                    break

            self.emit("action", f"{action_id} — {action.desc}")
            try:
                results.append(execute(action))
            except ExecutorError as e:
                self.emit("error", str(e))
                results.append(f"ERROR: {e}")
                break  # don't keep typing into a broken state
        return "\n".join(results) or "no actions executed"

    def _trim_history(self) -> None:
        # Drop oldest entries, but never let history start mid-exchange:
        # the first entry must be a plain user turn.
        while len(self.history) > MAX_HISTORY_ENTRIES:
            self.history.pop(0)
            while self.history and self.history[0]["role"] != "user":
                self.history.pop(0)
