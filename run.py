"""Launcher used for development, the right-click menu in dev mode, and as the PyInstaller entry point."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from oneclick.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
