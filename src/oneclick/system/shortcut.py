"""Create a desktop shortcut that launches the app (works for the built app and when run from source)."""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .. import APP_NAME
from .context_menu import launch_command

SHORTCUT_STEM = "Project Starter"


def _app_icon_file() -> Optional[Path]:
    """The .ico (Windows) / .icns (macOS) to use when running from source; the built app has its own."""
    root = Path(__file__).resolve().parents[3]
    name = "ProjectStarter.ico" if sys.platform == "win32" else "ProjectStarter.icns"
    icon = root / "packaging" / "icons" / name
    return icon if icon.is_file() else None


def desktop_dir() -> Path:
    if sys.platform == "win32":
        try:  # the registry knows about Desktops redirected to OneDrive; reading it is instant
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "Desktop")
            expanded = os.path.expandvars(str(value))
            if expanded:
                return Path(expanded)
        except OSError:
            pass
    return Path.home() / "Desktop"


def shortcut_path() -> Path:
    desktop = desktop_dir()
    if sys.platform == "win32":
        return desktop / f"{SHORTCUT_STEM}.lnk"
    if sys.platform == "darwin":
        return desktop / f"{SHORTCUT_STEM}.app" if getattr(sys, "frozen", False) else desktop / f"{SHORTCUT_STEM}.command"
    return desktop / "project-starter.desktop"


def shortcut_exists() -> bool:
    return shortcut_path().exists()


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def create_desktop_shortcut() -> Path:
    """Create (or replace) the shortcut and return its path. Raises OSError/RuntimeError with a readable message."""
    target = shortcut_path()
    command = launch_command()
    desktop = target.parent
    desktop.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        exe, args = command[0], subprocess.list2cmdline(command[1:])
        icon = command[0] if getattr(sys, "frozen", False) else _app_icon_file()
        script = (
            f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(str(target))}); "
            f"$s.TargetPath = {_ps_quote(exe)}; "
            f"$s.Arguments = {_ps_quote(args)}; "
            f"$s.WorkingDirectory = {_ps_quote(str(Path(exe).parent))}; "
            f"$s.Description = {_ps_quote(APP_NAME)}; "
            + (f"$s.IconLocation = {_ps_quote(str(icon) + ',0')}; " if icon else "")
            + "$s.Save()"
        )
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=30)
        if result.returncode != 0 or not target.exists():
            raise RuntimeError(result.stderr.strip() or "PowerShell could not create the shortcut.")
        return target

    if sys.platform == "darwin":
        if getattr(sys, "frozen", False):
            # The app bundle is three levels up from the executable: X.app/Contents/MacOS/exe
            bundle = Path(sys.executable).resolve().parents[2]
            if target.exists() or target.is_symlink():
                target.unlink()
            os.symlink(bundle, target)
            return target
        shell = " ".join(shlex.quote(part) for part in command)
        target.write_text(f"#!/bin/bash\n# Launches {APP_NAME} from source.\n{shell} &\nosascript -e 'tell application \"Terminal\" to close first window' >/dev/null 2>&1 &\n", encoding="utf-8")
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return target

    # Linux / other: freedesktop .desktop file
    exec_line = " ".join(shlex.quote(part) for part in command)
    icon = _app_icon_file()
    target.write_text(
        "[Desktop Entry]\nType=Application\n"
        f"Name={APP_NAME}\nExec={exec_line}\nTerminal=false\n" + (f"Icon={icon}\n" if icon else ""),
        encoding="utf-8",
    )
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    return target


def remove_desktop_shortcut() -> None:
    target = shortcut_path()
    if target.is_symlink() or target.exists():
        target.unlink()
