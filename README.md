# LogicAssistant

Control Logic Pro with your voice. Dictation via [Wispr Flow](https://wisprflow.ai), reasoning via Claude, execution via Logic's own key commands — no plugins, no Logic internals.

```
You speak → Wispr Flow types it → Claude picks actions → keystrokes hit Logic
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY
```

**One-time macOS permission:** System Settings → Privacy & Security → Accessibility → enable your terminal app (it sends keystrokes on your behalf). You may also need Automation permission for "System Events" — macOS will prompt on first run.

## Usage

```bash
# 1. Smoke-test a single key command against a real Logic project (do this first)
python smoke_test.py play_stop
python smoke_test.py --list

# 2. Run the assistant
python -m logic_assistant
```

With Logic open, focus the terminal, hold your Wispr Flow hotkey, and say:
> "Create a software instrument track and open the library"

Typed commands work identically. `quit` exits.

## Adding capabilities

Add a line to `commands.yaml` — Claude's tools are generated from it. For actions without default Logic shortcuts, assign one in Logic (Option+K) and record it here.

## Dry-run mode

`LOGIC_DRY_RUN=1 python -m logic_assistant` prints the AppleScript instead of executing — useful for testing without Logic open.
