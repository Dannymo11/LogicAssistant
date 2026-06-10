"""Read Logic Pro's track list via the macOS accessibility API (read-only).

Primary strategy: Logic exposes the track header area as an AXLayoutArea
(description "Tracks"); each child layout item is one track header whose
description contains the track name, with AXSelected reflecting selection.

Fallback strategy: breadth-first scan for any elements whose description
matches 'Track N …'. If your ax_probe.py dump shows a different shape,
adjust TRACK_DESC_RE / AREA_DESC below — everything else stays the same.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections import deque
from dataclasses import dataclass

AREA_DESC = "Tracks"
TRACK_DESC_RE = re.compile(r'Track\s+(\d+)\s+["“”\'](.+?)["“”\']')
MAX_SCAN_NODES = 6000


class TracksError(RuntimeError):
    pass


@dataclass
class Track:
    index: int
    name: str
    selected: bool

    def to_dict(self) -> dict:
        return {"index": self.index, "name": self.name, "selected": self.selected}


# ── AX plumbing ──────────────────────────────────────────────


def _ax():
    try:
        from ApplicationServices import (  # type: ignore
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
        )
    except ImportError as e:
        raise TracksError(
            "pyobjc ApplicationServices framework missing — "
            "run: pip install pyobjc-framework-ApplicationServices"
        ) from e
    return AXUIElementCreateApplication, AXUIElementCopyAttributeValue


def _attr(copy_fn, element, name):
    err, value = copy_fn(element, name, None)
    return value if err == 0 else None


def _logic_pid() -> int:
    app_name = os.environ.get("LOGIC_APP_NAME", "Logic Pro")
    out = subprocess.run(
        ["pgrep", "-x", app_name], capture_output=True, text=True
    ).stdout.strip()
    if not out:
        raise TracksError(f"{app_name} is not running")
    return int(out.splitlines()[0])


# ── reading ──────────────────────────────────────────────────


def get_tracks() -> list[Track]:
    if os.environ.get("LOGIC_DRY_RUN", "").strip() not in ("", "0", "false"):
        return [  # deterministic fake session for testing
            Track(1, "Drums", False),
            Track(2, "Bass", True),
            Track(3, "Vocals", False),
        ]

    create_app, copy_fn = _ax()
    app = create_app(_logic_pid())
    windows = _attr(copy_fn, app, "AXWindows") or []
    if not windows:
        raise TracksError(
            "no AX windows — check Accessibility permission for your terminal"
        )

    for window in windows:
        tracks = _tracks_from_layout_area(copy_fn, window)
        if tracks:
            return tracks
    for window in windows:
        tracks = _tracks_by_scan(copy_fn, window)
        if tracks:
            return tracks
    raise TracksError(
        "could not locate track headers in the AX tree — "
        "run ax_probe.py and adjust tracks.py heuristics"
    )


def _tracks_from_layout_area(copy_fn, root) -> list[Track]:
    area = _find(copy_fn, root, lambda el: (
        _attr(copy_fn, el, "AXRole") == "AXLayoutArea"
        and str(_attr(copy_fn, el, "AXDescription") or "") == AREA_DESC
    ))
    if area is None:
        return []
    tracks = []
    for i, item in enumerate(_attr(copy_fn, area, "AXChildren") or [], start=1):
        desc = str(_attr(copy_fn, item, "AXDescription") or "")
        match = TRACK_DESC_RE.search(desc)
        name = match.group(2) if match else (desc or f"Track {i}")
        selected = bool(_attr(copy_fn, item, "AXSelected"))
        tracks.append(Track(index=i, name=name, selected=selected))
    return tracks


def _tracks_by_scan(copy_fn, root) -> list[Track]:
    tracks = []
    for el in _iter_nodes(copy_fn, root):
        desc = str(_attr(copy_fn, el, "AXDescription") or "")
        match = TRACK_DESC_RE.search(desc)
        if match:
            tracks.append(
                Track(
                    index=int(match.group(1)),
                    name=match.group(2),
                    selected=bool(_attr(copy_fn, el, "AXSelected")),
                )
            )
    tracks.sort(key=lambda t: t.index)
    # de-dup (the same header can appear in nested elements)
    seen: set[int] = set()
    return [t for t in tracks if not (t.index in seen or seen.add(t.index))]


def _find(copy_fn, root, predicate):
    for el in _iter_nodes(copy_fn, root):
        if predicate(el):
            return el
    return None


def _iter_nodes(copy_fn, root):
    queue = deque([root])
    count = 0
    while queue and count < MAX_SCAN_NODES:
        el = queue.popleft()
        count += 1
        yield el
        queue.extend(_attr(copy_fn, el, "AXChildren") or [])
