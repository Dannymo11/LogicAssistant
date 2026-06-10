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

# 2. Run the assistant (terminal)
python -m logic_assistant

# 3. Or the floating HUD (always-on-top panel over Logic)
python -m logic_assistant --hud
```

With Logic open, focus the input, hold your Wispr Flow hotkey, and say:
> "Create a software instrument track and open the library"

**Auto-send:** Wispr Flow types but never presses Enter, so both front-ends
submit automatically after ~1.2 s of input silence. Enter still sends
immediately. Tune with `LOGIC_AUTOSEND_MS` in `.env`.

Typed commands work identically. `quit` exits the terminal version.

## Local model (low latency)

The LLM backend is pluggable. Default is Claude; for sub-second responses run
Gemma 4 locally via [Ollama](https://ollama.com):

```bash
ollama pull gemma4:26b        # 26B MoE — best local quality (check tag with `ollama list`)
ollama pull gemma4:e4b        # small fallback for when Logic eats your RAM
```

Then in `.env`: `LOGIC_BACKEND=ollama` and `LOGIC_LOCAL_MODEL=gemma4:26b`.
Anything OpenAI-compatible works (LM Studio: set `LOGIC_LOCAL_URL`).

**RAM note (36 GB Mac):** quantized 26B MoE wants roughly 17–20 GB; a large
Logic project can claim 10+ GB. If you hear swapping or responses slow down
mid-session, switch `LOGIC_LOCAL_MODEL=gemma4:e4b` (~4 GB) — for 22-action
tool selection it's nearly as reliable and even faster.

## Track awareness ("mute the drums")

The agent has a read-only `get_tracks` tool that reads track names and the
current selection via macOS accessibility, then navigates by arrow-key steps.
Logic's AX tree is undocumented, so if `get_tracks` errors on your setup:

```bash
python ax_probe.py    # with a Logic project open; writes ax_dump.txt
```

…and adjust the heuristics at the top of `logic_assistant/tracks.py` to match
what the dump shows (look for elements whose description contains your track
names). In dry-run mode `get_tracks` returns a fake 3-track session.

## Adding capabilities

Add a line to `commands.yaml` — Claude's tools are generated from it. For actions without default Logic shortcuts, assign one in Logic (Option+K) and record it here.

## Dry-run mode

`LOGIC_DRY_RUN=1 python -m logic_assistant` prints the AppleScript instead of executing — useful for testing without Logic open.
