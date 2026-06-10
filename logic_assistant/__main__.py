import sys


def main() -> int:
    if "--hud" in sys.argv:
        from .hud import main as run
    else:
        from .cli import main as run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
