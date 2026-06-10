"""Floating HUD front-end: a small always-on-top panel over Logic.

Same engine as the CLI (LogicAgent); pywebview renders the UI. The input box
auto-sends after LOGIC_AUTOSEND_MS of silence (Wispr Flow types but never
presses Enter); Enter sends immediately. Risky actions show inline
Yes/No buttons.
"""

from __future__ import annotations

import json
import os
import threading

from dotenv import load_dotenv

from .agent import LogicAgent
from .executor import dry_run_enabled
from .registry import Registry

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  :root { --bg:#141417; --panel:#1d1d22; --text:#e8e8ec; --dim:#8a8a93;
          --accent:#4fc3f7; --warn:#ffb74d; --err:#ef5350; }
  * { box-sizing:border-box; margin:0; }
  body { background:var(--bg); color:var(--text); border-radius:12px;
         font:13px/1.45 -apple-system, "SF Pro Text", sans-serif;
         height:100vh; display:flex; flex-direction:column; overflow:hidden;
         border:1px solid #2c2c33; }
  #bar { padding:9px 12px; display:flex; align-items:center; gap:8px;
         background:var(--panel); cursor:grab; user-select:none; }
  #dot { width:8px; height:8px; border-radius:50%; background:#4caf50;
         transition:background .2s; }
  #dot.busy { background:var(--warn); animation:pulse 1s infinite; }
  @keyframes pulse { 50% { opacity:.4; } }
  #title { font-weight:600; font-size:12px; letter-spacing:.3px; }
  #mode { color:var(--dim); font-size:11px; margin-left:auto; }
  #log { flex:1; overflow-y:auto; padding:10px 12px; display:flex;
         flex-direction:column; gap:6px; }
  .you   { color:var(--text); }
  .you::before   { content:"you  "; color:#81c784; font-weight:600; }
  .reply { color:var(--accent); }
  .reply::before { content:"logic  "; color:var(--accent); font-weight:600; }
  .action { color:var(--dim); font-size:12px; padding-left:8px; }
  .action::before { content:"▸ "; color:var(--accent); }
  .result { color:var(--dim); font-size:12px; padding-left:8px; }
  .error { color:var(--err); font-size:12px; }
  #confirm { display:none; padding:8px 12px; background:#2a2113;
             border-top:1px solid #3a3a42; align-items:center; gap:8px; }
  #confirm.show { display:flex; }
  #confirm span { color:var(--warn); flex:1; }
  #confirm button { border:0; border-radius:6px; padding:5px 14px;
                    font-weight:600; cursor:pointer; }
  #yes { background:var(--warn); color:#141417; }
  #no  { background:#3a3a42; color:var(--text); }
  #inputrow { padding:10px 12px; background:var(--panel);
              border-top:1px solid #2c2c33; }
  #input { width:100%; background:#26262d; border:1px solid #34343c;
           border-radius:8px; color:var(--text); padding:8px 10px;
           font-size:13px; outline:none; }
  #input:focus { border-color:var(--accent); }
</style>
</head>
<body>
  <div id="bar" class="pywebview-drag-region">
    <div id="dot"></div><div id="title">LogicAssistant</div><div id="mode"></div>
  </div>
  <div id="log"></div>
  <div id="confirm">
    <span id="confirm-text"></span>
    <button id="yes" onclick="answer(true)">Yes</button>
    <button id="no" onclick="answer(false)">No</button>
  </div>
  <div id="inputrow">
    <input id="input" placeholder="speak (Wispr Flow) or type…" autofocus>
  </div>
<script>
  var AUTOSEND_MS = __AUTOSEND_MS__;
  var input = document.getElementById('input');
  var log = document.getElementById('log');
  var timer = null;

  input.addEventListener('input', function () {
    clearTimeout(timer);
    if (input.value.trim()) timer = setTimeout(send, AUTOSEND_MS);
  });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); send(); }
  });

  function send() {
    clearTimeout(timer);
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    window.pywebview.api.submit(text);
  }

  /* ── called from Python ── */
  function addEntry(kind, text) {
    var div = document.createElement('div');
    div.className = kind;
    div.textContent = text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }
  function setBusy(busy) {
    document.getElementById('dot').className = busy ? 'busy' : '';
  }
  function setMode(text) {
    document.getElementById('mode').textContent = text;
  }
  function showConfirm(prompt) {
    document.getElementById('confirm-text').textContent = prompt;
    document.getElementById('confirm').className = 'show';
  }
  function answer(yes) {
    document.getElementById('confirm').className = '';
    window.pywebview.api.answer_confirm(yes);
    input.focus();
  }
</script>
</body>
</html>"""


class HudApi:
    """JS↔Python bridge. pywebview runs each JS call on its own thread."""

    def __init__(self) -> None:
        self.window = None  # set after create_window
        self.agent: LogicAgent | None = None
        self._busy = threading.Lock()  # one request at a time
        self._confirm_event: threading.Event | None = None
        self._confirm_answer = False

    # ── called from JS ───────────────────────────────────────

    def submit(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self._busy:
            self._js("addEntry", "you", text)
            self._js("setBusy", True)
            try:
                reply = self.agent.handle(text)
                if reply:
                    self._js("addEntry", "reply", reply)
            except Exception as e:  # surface, don't crash the HUD
                self._js("addEntry", "error", str(e))
            finally:
                self._js("setBusy", False)

    def answer_confirm(self, yes: bool) -> None:
        self._confirm_answer = bool(yes)
        if self._confirm_event:
            self._confirm_event.set()

    # ── agent callbacks (run on the submit thread) ───────────

    def confirm(self, prompt: str) -> bool:
        self._confirm_event = threading.Event()
        self._confirm_answer = False
        self._js("showConfirm", prompt)
        self._confirm_event.wait(timeout=120)  # auto-decline if ignored
        return self._confirm_answer

    def emit(self, kind: str, text: str) -> None:
        self._js("addEntry", kind, text)

    # ── plumbing ─────────────────────────────────────────────

    def _js(self, fn: str, *args) -> None:
        if self.window is not None:
            payload = ", ".join(json.dumps(a) for a in args)
            self.window.evaluate_js(f"{fn}({payload})")


def main() -> int:
    import webview  # lazy: heavy dependency, macOS-specific backend

    load_dotenv()
    registry = Registry.load("commands.yaml")

    api = HudApi()
    api.agent = LogicAgent(registry, confirm=api.confirm, emit=api.emit)

    autosend_ms = os.environ.get("LOGIC_AUTOSEND_MS", "1200")
    html = HTML.replace("__AUTOSEND_MS__", str(int(autosend_ms)))

    window = webview.create_window(
        "LogicAssistant",
        html=html,
        width=430,
        height=380,
        on_top=True,
        frameless=True,
        easy_drag=False,  # drag handled by the title bar region
        resizable=True,
    )
    api.window = window

    def on_shown() -> None:
        mode = "dry-run" if dry_run_enabled() else f"{len(registry.actions)} actions"
        api._js("setMode", f"{api.agent.backend.label} · {mode}")

    window.events.shown += on_shown
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
