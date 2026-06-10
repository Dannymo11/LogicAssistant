"""Pluggable LLM backends behind a neutral conversation format.

History entries (backend-neutral, owned by LogicAgent):
    {"role": "user",      "content": str}
    {"role": "assistant", "msg": AssistantMsg}
    {"role": "tool",      "tool_call_id": str, "content": str}

Select with LOGIC_BACKEND:
    claude (default)          → Anthropic API
    ollama | local | lmstudio → any OpenAI-compatible server
                                (LOGIC_LOCAL_URL, LOGIC_LOCAL_MODEL)
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field

import requests


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class AssistantMsg:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


# ── Anthropic ────────────────────────────────────────────────


class ClaudeBackend:
    def __init__(self, tool_specs: list[dict], system: str, client=None, model: str | None = None):
        from anthropic import Anthropic

        self.client = client or Anthropic()
        self.model = model or os.environ.get("LOGIC_MODEL", "claude-sonnet-4-6")
        self.system = system
        self.tools = [
            {
                "name": spec["name"],
                "description": spec["description"],
                "input_schema": spec["parameters"],
            }
            for spec in tool_specs
        ]
        self.label = self.model

    def chat(self, history: list[dict]) -> AssistantMsg:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self.system,
            tools=self.tools,
            messages=self._serialize(history),
        )
        text = " ".join(b.text for b in response.content if b.type == "text").strip()
        calls = [
            ToolCall(id=b.id, name=b.name, input=b.input)
            for b in response.content
            if b.type == "tool_use"
        ]
        return AssistantMsg(text=text, tool_calls=calls)

    @staticmethod
    def _serialize(history: list[dict]) -> list[dict]:
        msgs: list[dict] = []
        for entry in history:
            role = entry["role"]
            if role == "user":
                msgs.append({"role": "user", "content": entry["content"]})
            elif role == "assistant":
                m: AssistantMsg = entry["msg"]
                blocks: list[dict] = []
                if m.text:
                    blocks.append({"type": "text", "text": m.text})
                for c in m.tool_calls:
                    blocks.append(
                        {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input}
                    )
                msgs.append({"role": "assistant", "content": blocks})
            elif role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": entry["tool_call_id"],
                    "content": entry["content"],
                }
                # tool results must arrive in the next user message; merge runs
                if msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], list):
                    msgs[-1]["content"].append(block)
                else:
                    msgs.append({"role": "user", "content": [block]})
        return msgs


# ── OpenAI-compatible (Ollama, LM Studio, …) ─────────────────


class OpenAICompatBackend:
    def __init__(
        self,
        tool_specs: list[dict],
        system: str,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ):
        self.base_url = (
            base_url or os.environ.get("LOGIC_LOCAL_URL", "http://localhost:11434/v1")
        ).rstrip("/")
        self.model = model or os.environ.get("LOGIC_LOCAL_MODEL", "gemma4:26b")
        self.api_key = api_key or os.environ.get("LOGIC_LOCAL_API_KEY", "ollama")
        self.system = system
        self.timeout = timeout
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": spec["name"],
                    "description": spec["description"],
                    "parameters": spec["parameters"],
                },
            }
            for spec in tool_specs
        ]
        self.label = f"local:{self.model}"

    def chat(self, history: list[dict]) -> AssistantMsg:
        payload = {
            "model": self.model,
            "messages": self._serialize(history),
            "tools": self.tools,
            "temperature": 0,  # tool selection should be deterministic
            "max_tokens": 512,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        msg = response.json()["choices"][0]["message"]

        text = (msg.get("content") or "").strip()
        calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments") or "{}"
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append(
                ToolCall(
                    id=tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    name=fn.get("name", ""),
                    input=args,
                )
            )
        return AssistantMsg(text=text, tool_calls=calls)

    def _serialize(self, history: list[dict]) -> list[dict]:
        msgs: list[dict] = [{"role": "system", "content": self.system}]
        for entry in history:
            role = entry["role"]
            if role == "user":
                msgs.append({"role": "user", "content": entry["content"]})
            elif role == "assistant":
                m: AssistantMsg = entry["msg"]
                out: dict = {"role": "assistant", "content": m.text or None}
                if m.tool_calls:
                    out["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.input),
                            },
                        }
                        for c in m.tool_calls
                    ]
                msgs.append(out)
            elif role == "tool":
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": entry["tool_call_id"],
                        "content": entry["content"],
                    }
                )
        return msgs


# ── factory ──────────────────────────────────────────────────


def make_backend(tool_specs: list[dict], system: str):
    choice = os.environ.get("LOGIC_BACKEND", "claude").strip().lower()
    if choice in ("ollama", "local", "lmstudio", "openai"):
        return OpenAICompatBackend(tool_specs, system)
    return ClaudeBackend(tool_specs, system)
