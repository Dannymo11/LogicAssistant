"""Load commands.yaml and generate Claude tool definitions from it."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_STEP_DELAY = 0.3
VALID_RISKS = {"low", "medium"}
TOOL_NAME = "run_logic_actions"


@dataclass
class Action:
    id: str
    keys: list[str]  # one entry per step, e.g. ["cmd+opt+a"] or ["u", "c", "space"]
    desc: str
    risk: str = "low"
    delay: float = DEFAULT_STEP_DELAY


@dataclass
class Registry:
    actions: dict[str, Action] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path = "commands.yaml") -> "Registry":
        raw = yaml.safe_load(Path(path).read_text())
        if not isinstance(raw, dict) or not raw:
            raise ValueError(f"{path}: expected a non-empty mapping of actions")

        actions: dict[str, Action] = {}
        for action_id, spec in raw.items():
            if not isinstance(spec, dict) or "keys" not in spec or "desc" not in spec:
                raise ValueError(f"{path}: action '{action_id}' needs 'keys' and 'desc'")
            keys = spec["keys"]
            if isinstance(keys, str):
                keys = [keys]
            risk = spec.get("risk", "low")
            if risk not in VALID_RISKS:
                raise ValueError(f"{path}: action '{action_id}' has invalid risk '{risk}'")
            actions[action_id] = Action(
                id=action_id,
                keys=[str(k) for k in keys],
                desc=str(spec["desc"]),
                risk=risk,
                delay=float(spec.get("delay", DEFAULT_STEP_DELAY)),
            )
        return cls(actions=actions)

    def get(self, action_id: str) -> Action:
        if action_id not in self.actions:
            raise KeyError(f"Unknown action '{action_id}'")
        return self.actions[action_id]

    def catalog(self) -> str:
        """Human/LLM-readable list of every available action."""
        lines = []
        for a in self.actions.values():
            risk_note = " (requires user confirmation)" if a.risk != "low" else ""
            lines.append(f"- {a.id}: {a.desc}{risk_note}")
        return "\n".join(lines)

    def tool_spec(self) -> dict:
        """Backend-neutral tool definition; each backend formats it."""
        return {
            "name": TOOL_NAME,
            "description": (
                "Execute one or more Logic Pro actions, in order. "
                "Available actions:\n" + self.catalog()
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": list(self.actions.keys()),
                        },
                        "description": "Action ids to execute, in order.",
                    }
                },
                "required": ["actions"],
            },
        }
