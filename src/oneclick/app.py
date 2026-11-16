"""Command-line entry point: ``oneclick [--dest FOLDER] [--name TEXT]``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import APP_NAME, __version__
from .system.logging_setup import setup_logging

log = logging.getLogger("oneclick")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oneclick", description=f"{APP_NAME}: create a new project folder from a template.")
    parser.add_argument("--dest", metavar="FOLDER", help="Destination folder to pre-fill (used by the right-click menu).")
    parser.add_argument("--name", metavar="TEXT", default="", help="Project name to pre-fill.")
    parser.add_argument("--install-context-menu", action="store_true", help="Add 'New project here' to the right-click menu.")
    parser.add_argument("--uninstall-context-menu", action="store_true", help="Remove it again.")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser


def clean_dest(value: Optional[str]) -> Optional[str]:
    """Tidy the folder passed on the command line.

    Windows passes ``"C:\\"`` (a drive root) as ``C:"`` because a backslash before a quote escapes
    it, so stray quotes are stripped and a bare drive letter gets its slash back.
    """
    if not value:
        return None
    text = value.strip().strip('"').strip()
    if len(text) == 2 and text[1] == ":":
        text += "\\"
    path = Path(text).expanduser()
    return str(path) if path.is_dir() else None


def _say(message: str) -> None:
    if sys.stdout is not None:  # a windowed (no console) build has no stdout
        print(message)


def _context_menu_command(install: bool) -> int:
    from .system.context_menu import get_context_menu

    menu = get_context_menu()
    try:
        menu.install() if install else menu.uninstall()
    except Exception as problem:
        log.exception("Right-click menu change failed")
        _say(f"Could not change the right-click menu: {problem}")
        return 1
    _say("Right-click menu added." if install else "Right-click menu removed.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging()
    if args.install_context_menu:
        return _context_menu_command(True)
    if args.uninstall_context_menu:
        return _context_menu_command(False)
    try:
        from .ui.main_window import run_gui

        return run_gui(clean_dest(args.dest), args.name)
    except Exception:
        log.exception("The app crashed on startup")
        raise
