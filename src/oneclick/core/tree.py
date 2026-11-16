"""Render a folder tree as text lines for the live preview."""

from __future__ import annotations

from typing import Iterable

from .models import TemplateEntry


class _Node:
    __slots__ = ("children", "is_dir")

    def __init__(self, is_dir: bool) -> None:
        self.children: dict[str, _Node] = {}
        self.is_dir = is_dir


def render_tree(root_label: str, entries: Iterable[TemplateEntry], max_lines: int = 200) -> list[str]:
    """Return ``root_label`` followed by an indented tree of ``entries``."""
    root = _Node(True)
    for entry in entries:
        node = root
        parts = entry.rel.split("/")
        for index, part in enumerate(parts):
            is_last = index == len(parts) - 1
            child = node.children.get(part)
            if child is None:
                child = node.children[part] = _Node(is_dir=(not is_last) or entry.is_dir)
            node = child

    lines = [root_label]

    def walk(node: _Node, prefix: str) -> None:
        ordered = sorted(node.children.items(), key=lambda kv: (not kv[1].is_dir, kv[0].casefold()))
        for index, (name, child) in enumerate(ordered):
            last = index == len(ordered) - 1
            lines.append(f"{prefix}{'└─ ' if last else '├─ '}{name}")
            if child.children:
                walk(child, prefix + ("   " if last else "│  "))

    walk(root, "")
    if len(lines) > max_lines:
        hidden = len(lines) - max_lines
        lines = lines[:max_lines] + [f"… and {hidden} more"]
    return lines
