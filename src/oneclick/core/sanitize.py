"""Make user input safe to use as a single folder-name component on Windows, macOS and Linux."""

from __future__ import annotations

import re
import unicodedata

from .errors import InvalidNameError

ILLEGAL_CHARS = frozenset('\\/:*?"<>|')
RESERVED_WINDOWS_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
MAX_COMPONENT_BYTES = 255


def sanitize_name(raw: str, replacement: str = "-") -> str:
    """Return ``raw`` with characters that break folder names removed or replaced.

    - control characters are dropped
    - ``\\ / : * ? " < > |`` become ``replacement``
    - runs of whitespace collapse to one space
    - leading/trailing spaces and dots are stripped (Windows rejects trailing ones,
      leading dots create hidden folders on macOS/Linux)
    """
    text = unicodedata.normalize("NFC", raw)
    text = "".join(" " if ch.isspace() else ch for ch in text)  # tabs/newlines act as spaces
    text = "".join(ch for ch in text if ord(ch) >= 32 and ch != "\x7f")
    text = "".join(replacement if ch in ILLEGAL_CHARS else ch for ch in text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .")


def validate_component(component: str) -> None:
    """Raise :class:`InvalidNameError` if ``component`` is unusable as a folder name."""
    if not component or not component.strip():
        raise InvalidNameError("The folder name is empty.")
    if component != component.strip(" ") or component.endswith("."):
        raise InvalidNameError("Folder names cannot start or end with a space or end with a dot.")
    bad = sorted({c for c in component if c in ILLEGAL_CHARS or ord(c) < 32})
    if bad:
        raise InvalidNameError(f"The folder name contains characters that are not allowed: {' '.join(bad)}")
    base = component.split(".")[0].strip().upper()
    if base in RESERVED_WINDOWS_NAMES:
        raise InvalidNameError(f"'{base}' is a reserved name on Windows. Please choose another name.")
    if len(component.encode("utf-8")) > MAX_COMPONENT_BYTES:
        raise InvalidNameError("The folder name is too long (the limit is 255 bytes).")
