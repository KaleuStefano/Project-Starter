"""Small shared data types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateEntry:
    """One item a template will create, relative to the project folder."""

    rel: str  # forward-slash separated, e.g. "01-Assets/01-Doc"
    is_dir: bool
    size: int = 0


@dataclass(frozen=True)
class CreatedEntry:
    """One item that was actually created on disk (used by undo)."""

    rel: str
    is_dir: bool
    size: int = 0
