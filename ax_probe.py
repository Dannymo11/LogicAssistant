#!/usr/bin/env python3
"""Dump Logic Pro's accessibility (AX) tree so we can find track headers.

Run on the Mac with a Logic project open:

    pip install pyobjc-framework-ApplicationServices
    python ax_probe.py            # writes ax_dump.txt, prints track candidates

Requires the same Accessibility permission the executor already uses.
"""

from __future__ import annotations

import re
import subprocess
import sys

MAX_DEPTH = 14
MAX_CHILDREN = 200  # per node, guard against huge mixers

try:
    from ApplicationServices import (  # type: ignore
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
    )
except ImportError:
    sys.exit(
        "pyobjc ApplicationServices framework missing.\n"
        "Run: pip install pyobjc-framework-ApplicationServices"
    )


def ax_attr(element, name):
    err, value = AXUIElementCopyAttributeValue(element, name, None)
    return value if err == 0 else None


def logic_pid() -> int:
    out = subprocess.run(
        ["pgrep", "-x", "Logic Pro"], capture_output=True, text=True
    ).stdout.strip()
    if not out:
        sys.exit("Logic Pro is not running.")
    return int(out.splitlines()[0])


def describe(element) -> str:
    parts = []
    for attr in ("AXRole", "AXSubrole", "AXTitle", "AXDescription", "AXValue",
                 "AXSelected", "AXFocused"):
        value = ax_attr(element, attr)
        if value not in (None, "", False):
            text = str(value)
            if len(text) > 120:
                text = text[:120] + "…"
            parts.append(f"{attr[2:]}={text!r}")
    return " ".join(parts) or "(no attributes)"


def walk(element, depth, lines, candidates):
    line = "  " * depth + describe(element)
    lines.append(line)

    desc = str(ax_attr(element, "AXDescription") or "")
    title = str(ax_attr(element, "AXTitle") or "")
    if re.search(r"\btrack\b", desc + " " + title, re.IGNORECASE):
        candidates.append(line)

    if depth >= MAX_DEPTH:
        lines.append("  " * (depth + 1) + "…(max depth)")
        return
    children = ax_attr(element, "AXChildren") or []
    for child in list(children)[:MAX_CHILDREN]:
        walk(child, depth + 1, lines, candidates)


def main() -> int:
    app = AXUIElementCreateApplication(logic_pid())
    windows = ax_attr(app, "AXWindows") or []
    if not windows:
        sys.exit(
            "No AX windows visible. Check Accessibility permission for your "
            "terminal (System Settings → Privacy & Security → Accessibility)."
        )

    lines: list[str] = []
    candidates: list[str] = []
    for i, window in enumerate(windows):
        lines.append(f"=== WINDOW {i}: {ax_attr(window, 'AXTitle')!r} ===")
        walk(window, 0, lines, candidates)

    with open("ax_dump.txt", "w") as f:
        f.write("\n".join(lines))

    print(f"Wrote {len(lines)} lines to ax_dump.txt\n")
    print(f"--- {len(candidates)} elements mentioning 'track' ---")
    for c in candidates[:40]:
        print(c.strip()[:160])
    if len(candidates) > 40:
        print(f"… and {len(candidates) - 40} more (see ax_dump.txt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
