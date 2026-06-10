#!/usr/bin/env python3
"""Fire a single registry action at Logic Pro — no Claude involved.

Usage:
    python smoke_test.py play_stop
    python smoke_test.py --list
    LOGIC_DRY_RUN=1 python smoke_test.py bounce   # print AppleScript only
"""

import sys

from logic_assistant.executor import execute, ExecutorError
from logic_assistant.registry import Registry


def main() -> int:
    reg = Registry.load("commands.yaml")

    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 1

    if sys.argv[1] == "--list":
        print(reg.catalog())
        return 0

    action_id = sys.argv[1]
    try:
        action = reg.get(action_id)
    except KeyError:
        print(f"Unknown action '{action_id}'. Run with --list to see all.")
        return 1

    print(f"→ {action.desc} ({', '.join(action.keys)})")
    try:
        print(execute(action))
    except ExecutorError as e:
        print(f"FAILED: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
