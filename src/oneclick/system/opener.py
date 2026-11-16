"""Open a folder in Explorer / Finder / the Linux file manager."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("oneclick")


def open_folder(path: Path) -> None:
    """Show ``path`` in the system file manager. Failures are logged, never raised."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]  # Windows only
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        log.exception("Could not open %s in the file manager", path)
