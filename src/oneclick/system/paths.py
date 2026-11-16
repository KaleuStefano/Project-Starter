"""Where the app keeps its settings, undo record and log, per operating system.

Set the ``ONECLICK_HOME`` environment variable to use a different folder (handy for a portable
install or for tests).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "ProjectStarter"


def user_data_dir() -> Path:
    override = os.environ.get("ONECLICK_HOME")
    if override:
        return Path(override)
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return base / APP_DIR_NAME


def settings_file() -> Path:
    return user_data_dir() / "settings.json"


def undo_file() -> Path:
    return user_data_dir() / "last_project.json"


def log_file() -> Path:
    return user_data_dir() / "oneclick.log"
