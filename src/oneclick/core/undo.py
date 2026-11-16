"""Undo the most recent project creation, but only while it is still untouched."""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import UndoError
from .models import CreatedEntry

log = logging.getLogger("oneclick")


@dataclass(frozen=True)
class UndoRecord:
    path: str
    folder_name: str
    created_at: str
    entries: tuple[CreatedEntry, ...]


class UndoStore:
    """Persists a single :class:`UndoRecord` in a JSON file."""

    def __init__(self, file: Path) -> None:
        self.file = Path(file)

    def save(self, record: UndoRecord) -> None:
        payload = {
            "path": record.path,
            "folder_name": record.folder_name,
            "created_at": record.created_at,
            "entries": [{"rel": e.rel, "is_dir": e.is_dir, "size": e.size} for e in record.entries],
        }
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, self.file)
        except OSError:
            log.exception("Could not save the undo record")  # undo is a convenience; never block creation

    def load(self) -> Optional[UndoRecord]:
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
            entries = tuple(
                CreatedEntry(str(e["rel"]), bool(e["is_dir"]), int(e.get("size", 0))) for e in data["entries"]
            )
            return UndoRecord(str(data["path"]), str(data["folder_name"]), str(data["created_at"]), entries)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("Ignoring unreadable undo record %s", self.file)
            return None

    def clear(self) -> None:
        try:
            self.file.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            log.exception("Could not remove the undo record")


def make_record(project_path: Path, entries: list[CreatedEntry], now: Optional[dt.datetime] = None) -> UndoRecord:
    return UndoRecord(
        path=str(project_path),
        folder_name=project_path.name,
        created_at=(now or dt.datetime.now()).isoformat(timespec="seconds"),
        entries=tuple(entries),
    )


def _actual_entries(root: Path) -> dict[str, tuple[bool, int]]:
    found: dict[str, tuple[bool, int]] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        prefix = current.relative_to(root).as_posix()
        prefix = "" if prefix == "." else prefix + "/"
        for d in dirnames:
            found[prefix + d] = (True, 0)
        for f in filenames:
            try:
                size = (current / f).stat().st_size
            except OSError:
                size = -1
            found[prefix + f] = (False, size)
    return found


def check_untouched(record: UndoRecord) -> list[str]:
    """Return reasons the project can no longer be undone safely (empty list means it is safe)."""
    root = Path(record.path)
    if not root.is_dir():
        return ["The project folder no longer exists."]
    if root.name != record.folder_name or len(root.parts) < 2:
        return ["The undo record does not match the folder; refusing to delete anything."]
    expected = {e.rel: e for e in record.entries}
    actual = _actual_entries(root)
    problems: list[str] = []
    extra = sorted(set(actual) - set(expected))
    if extra:
        sample = ", ".join(extra[:3]) + (" …" if len(extra) > 3 else "")
        problems.append(f"{len(extra)} item(s) were added since it was created ({sample}).")
    changed = sorted(
        rel for rel, entry in expected.items() if rel in actual and not entry.is_dir and actual[rel][1] != entry.size
    )
    if changed:
        problems.append(f"{len(changed)} file(s) were modified ({', '.join(changed[:3])}).")
    kind_changed = sorted(rel for rel, entry in expected.items() if rel in actual and actual[rel][0] != entry.is_dir)
    if kind_changed:
        problems.append(f"{len(kind_changed)} item(s) changed type ({', '.join(kind_changed[:3])}).")
    return problems


def remove_entries(root: Path, entries: list[CreatedEntry], remove_root: bool = True) -> list[str]:
    """Delete exactly ``entries`` (files first, then folders deepest-first), never recursively.

    Folders that are not empty are left in place. Returns messages for anything that
    could not be removed.
    """
    failures: list[str] = []
    files = [e for e in entries if not e.is_dir]
    dirs = sorted((e for e in entries if e.is_dir), key=lambda e: e.rel.count("/"), reverse=True)
    for entry in files:
        target = root.joinpath(*entry.rel.split("/"))
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            failures.append(f"{entry.rel}: {error}")
    for entry in dirs:
        target = root.joinpath(*entry.rel.split("/"))
        try:
            target.rmdir()
        except FileNotFoundError:
            pass
        except OSError as error:
            failures.append(f"{entry.rel}: {error}")
    if remove_root:
        try:
            root.rmdir()
        except FileNotFoundError:
            pass
        except OSError as error:
            failures.append(f"{root.name}: {error}")
    return failures


def undo_last(store: UndoStore) -> Path:
    """Remove the last created project if it is untouched. Returns the removed path."""
    record = store.load()
    if record is None:
        raise UndoError("There is nothing to undo.")
    problems = check_untouched(record)
    if problems:
        raise UndoError("The last project can't be undone safely:\n- " + "\n- ".join(problems))
    failures = remove_entries(Path(record.path), list(record.entries))
    if failures:
        raise UndoError("Some items could not be removed:\n- " + "\n- ".join(failures))
    store.clear()
    return Path(record.path)
