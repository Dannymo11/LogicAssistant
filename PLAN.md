# Logic Voice Assistant — Prototype Plan

A voice-driven assistant that controls Logic Pro by speaking commands. Dictation handled by Wispr Flow, reasoning by Claude (tool use), execution by macOS keystroke automation of Logic's key commands. No Logic internals, no plugins, no MIDI scripting.

**Target: working demo in 2 days, video-ready by day 3.**

## Architecture

```
You speak (Wispr Flow push-to-talk)
        │  Flow types transcript into the terminal prompt
        ▼
┌─────────────────────┐
│  assistant.py (REPL) │  rich CLI: shows transcript, plan, actions
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  Claude API          │  tool use: picks 1..n actions from registry,
│  (claude-sonnet-4-6) │  can chain them (macro), asks before risky ops
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  executor.py         │  osascript: activate Logic → send keystrokes
│                      │  → restore focus to terminal
└─────────┬───────────┘
          ▼
      Logic Pro
```

Wispr Flow removes the entire STT layer: its own hotkey is the push-to-talk, and it types into whatever is focused. The assistant is just a text REPL — which also gives us a typed fallback for free if the mic misbehaves during filming.

## Components

### 1. Key-command registry (`commands.yaml`)
Single source of truth. Each entry: id, description (what Claude sees), keystroke(s), risk level.

```yaml
play_stop:        {keys: "space",        desc: "Toggle play/stop", risk: low}
record:           {keys: "r",            desc: "Start recording",  risk: medium}
toggle_cycle:     {keys: "c",            desc: "Toggle cycle/loop mode", risk: low}
toggle_metronome: {keys: "k",            desc: "Toggle metronome", risk: low}
mute_track:       {keys: "m",            desc: "Mute selected track", risk: low}
solo_track:       {keys: "s",            desc: "Solo selected track", risk: low}
new_audio_track:  {keys: "cmd+opt+a",    desc: "New audio track", risk: low}
new_inst_track:   {keys: "cmd+opt+s",    desc: "New software instrument track", risk: low}
open_mixer:       {keys: "x",            desc: "Show/hide mixer", risk: low}
open_piano_roll:  {keys: "p",            desc: "Show/hide piano roll", risk: low}
open_library:     {keys: "y",            desc: "Show/hide library (patches)", risk: low}
go_to_start:      {keys: "return",       desc: "Playhead to beginning", risk: low}
undo:             {keys: "cmd+z",        desc: "Undo", risk: medium}
save:             {keys: "cmd+s",        desc: "Save project", risk: low}
bounce:           {keys: "cmd+b",        desc: "Bounce/export project", risk: medium}
select_next_track: {keys: "down",        desc: "Select next track", risk: low}
select_prev_track: {keys: "up",          desc: "Select previous track", risk: low}
```

Verify each against your Logic install (Logic Pro → Settings → Key Commands, Option+K). Anything unbound by default (e.g. "go to bar N", tempo nudge): assign a custom binding in Logic, record it in the registry. The registry-driven design means adding a capability = adding a YAML line.

### 2. Executor (`executor.py`)
- `osascript -e 'tell application "Logic Pro" to activate'`, short delay, then `System Events` keystrokes/key codes; finally re-activate the terminal so Flow dictation keeps landing in the REPL.
- Parses `"cmd+opt+a"` → AppleScript `keystroke "a" using {command down, option down}`; special keys (space, return, arrows) → `key code`.
- Supports sequences with delays for multi-step macros.
- One-time setup: grant the terminal app Accessibility permission (System Settings → Privacy & Security → Accessibility), and turn OFF "Musical Typing" assumptions — confirm Logic's key commands fire when Logic is frontmost.

### 3. Agent loop (`assistant.py`)
- Builds Claude tool definitions from the registry automatically + one `run_sequence` tool for chained actions ("mute this track and play from the top" → `mute_track`, `go_to_start`, `play_stop`).
- Maintains conversation history → follow-ups like "undo that" work.
- `risk: medium` actions (record, bounce, undo) get a one-line confirm in the CLI; everything else fires immediately. Keeps the demo fast but never destructive.
- Rich terminal output: what you said → what Claude decided → what was executed. This *is* the video's visual narrative.

### 4. Config
`.env` for `ANTHROPIC_API_KEY`; `requirements.txt`: `anthropic`, `pyyaml`, `rich`, `python-dotenv`. Nothing else.

## Milestones

**M0 — Scaffold (30 min):** repo layout, deps, .env, README.
**M1 — Executor (half day):** keystroke sender works; smoke test script (`python smoke_test.py play_stop`) toggles playback in a real Logic project. *This is the riskiest piece — do it first.*
**M2 — Agent loop (half day):** Claude + registry tools + REPL. Test typed commands end-to-end.
**M3 — Wispr Flow integration (1 hr):** just configuration — confirm Flow types cleanly into the REPL, tune Flow's vocabulary if it mangles terms like "piano roll".
**M4 — Demo hardening (half day):** pick the 5 video moments, add 2–3 custom key commands they need, rehearse, handle the failure modes you hit.

## Demo script (the 2-min video spine)

1. "Create a software instrument track and open the library" — two actions chained.
2. "Loop the selection and play it back" — `U` (set locators) + cycle + play. *(verify `U` binding)*
3. "Mute the drums and solo the bass" — track selection + mute/solo, shows multi-step reasoning.
4. "I hate that — undo it and play from the top" — conversational memory + confirm flow.
5. "Save and bounce the project" — finale.

Camera on: you talking, terminal showing Claude's reasoning, Logic responding instantly. The terminal output design matters as much as the functionality.

## Risks

- **Keystrokes land in wrong app** → executor always activates Logic first, restores focus after; rehearse with the exact window layout you'll film.
- **Focused-track ambiguity** ("mute the drums" — which track is selected?) → for the demo, pre-select or use up/down navigation; "select track by name" is a stretch goal (AppleScript UI scripting can read track headers — only if time permits).
- **Key command drift** (custom mappings differ from defaults) → smoke-test every registry entry on your machine before wiring Claude to it; export your Logic key commands as backup.
- **Latency** (~1–2 s Claude round trip) → fine; use the gap — the CLI prints "thinking" with the transcript, reads as deliberate in the video.

## Out of scope (say no)

Tempo/parameter dials via mouse automation, plugin parameter control, wake word, GUI app, reading Logic project state. All possible, none needed for the video.
