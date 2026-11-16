"""Naming engine: token patterns, the project counter and case styles.

A pattern is plain text with ``{tokens}``::

    {YY}{sep}{NN}{sep}{name}   ->  26-12-My Project

Tokens: ``{YYYY} {YY} {MM} {DD}`` (date), ``{NN}`` (project counter),
``{name}`` (what the user typed) and ``{sep}`` (the scheme's separator).
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, Iterable, Optional

from .errors import InvalidNameError, InvalidPatternError
from .sanitize import ILLEGAL_CHARS, sanitize_name, validate_component

KNOWN_TOKENS = ("YYYY", "YY", "MM", "DD", "NN", "name", "sep")
TOKEN_HELP = {
    "YYYY": "four-digit year (2026)",
    "YY": "two-digit year (26)",
    "MM": "month (01-12)",
    "DD": "day of month (01-31)",
    "NN": "project counter (01, 02, ...)",
    "name": "the project name you type",
    "sep": "the separator character",
}
CASE_STYLES = {
    "keep": "Keep as typed",
    "title": "Title Case",
    "kebab": "kebab-case",
    "snake": "snake_case",
}
COUNTER_SCOPES = {
    "continue": "Continue numbering (highest existing number + 1)",
    "per_year": "Restart every year",
}
DEFAULT_PATTERN = "{YY}{sep}{NN}{sep}{name}"

_TOKEN_RE = re.compile(r"\{([^{}]*)\}")
Part = tuple[str, str]  # ("lit" | "tok", text)


def parse_pattern(pattern: str) -> list[Part]:
    """Split ``pattern`` into literal and token parts, validating it."""
    if not pattern.strip():
        raise InvalidPatternError("The naming pattern is empty.")
    parts: list[Part] = []
    pos = 0
    for match in _TOKEN_RE.finditer(pattern):
        if match.start() > pos:
            parts.append(("lit", pattern[pos : match.start()]))
        token = match.group(1)
        if token not in KNOWN_TOKENS:
            raise InvalidPatternError(
                f"Unknown token {{{token}}}. Available tokens: " + ", ".join("{" + t + "}" for t in KNOWN_TOKENS)
            )
        parts.append(("tok", token))
        pos = match.end()
    if pos < len(pattern):
        parts.append(("lit", pattern[pos:]))

    for kind, text in parts:
        if kind != "lit":
            continue
        if "{" in text or "}" in text:
            raise InvalidPatternError("The pattern has an unmatched curly brace.")
        bad = sorted({c for c in text if c in ILLEGAL_CHARS or ord(c) < 32})
        if bad:
            raise InvalidPatternError(f"The pattern contains characters not allowed in folder names: {' '.join(bad)}")

    counts = Counter(text for kind, text in parts if kind == "tok")
    if counts["name"] != 1:
        raise InvalidPatternError("The pattern must contain {name} exactly once.")
    for token in ("YYYY", "YY", "MM", "DD", "NN"):
        if counts[token] > 1:
            raise InvalidPatternError(f"{{{token}}} can only appear once in the pattern.")
    if counts["YYYY"] and counts["YY"]:
        raise InvalidPatternError("Use either {YYYY} or {YY}, not both.")
    return parts


@dataclass(frozen=True)
class NamingScheme:
    """A named, saved way of building folder names."""

    id: str
    label: str
    pattern: str = DEFAULT_PATTERN
    sep: str = "-"
    pad: int = 2
    case: str = "keep"
    counter_scope: str = "continue"
    builtin: bool = False

    def validate(self) -> list[Part]:
        """Return the parsed pattern or raise :class:`InvalidPatternError`."""
        parts = parse_pattern(self.pattern)
        if any(c in ILLEGAL_CHARS or ord(c) < 32 for c in self.sep):
            raise InvalidPatternError("The separator contains characters not allowed in folder names.")
        if not 1 <= self.pad <= 8:
            raise InvalidPatternError("The counter width must be between 1 and 8 digits.")
        if self.case not in CASE_STYLES:
            raise InvalidPatternError(f"Unknown case style '{self.case}'.")
        if self.counter_scope not in COUNTER_SCOPES:
            raise InvalidPatternError(f"Unknown counter scope '{self.counter_scope}'.")
        return parts

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "pattern": self.pattern,
            "sep": self.sep,
            "pad": self.pad,
            "case": self.case,
            "counter_scope": self.counter_scope,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NamingScheme":
        defaults = cls(id="", label="")
        try:
            pad = int(data.get("pad", defaults.pad))
        except (TypeError, ValueError):
            pad = defaults.pad
        return cls(
            id=str(data.get("id", "")),
            label=str(data.get("label", "")) or str(data.get("id", "")),
            pattern=str(data.get("pattern", defaults.pattern)),
            sep=str(data.get("sep", defaults.sep)),
            pad=pad,
            case=str(data.get("case", defaults.case)),
            counter_scope=str(data.get("counter_scope", defaults.counter_scope)),
        )

    def with_changes(self, **changes: Any) -> "NamingScheme":
        return replace(self, **changes)


BUILTIN_SCHEMES: tuple[NamingScheme, ...] = (
    NamingScheme("default", "YY-NN-Name", builtin=True),
    NamingScheme("year4", "YYYY-NN-Name", pattern="{YYYY}{sep}{NN}{sep}{name}", builtin=True),
    NamingScheme("yymm", "YYMM-NN-Name", pattern="{YY}{MM}{sep}{NN}{sep}{name}", builtin=True),
    NamingScheme("count-only", "NN-Name (no year)", pattern="{NN}{sep}{name}", builtin=True),
)


def apply_case(name: str, style: str) -> str:
    """Apply a case style to the user's project name."""
    if style == "keep":
        return name
    if style == "title":
        return " ".join(word[:1].upper() + word[1:] for word in name.split(" "))
    words = [w for w in re.split(r"[\s_\-]+", name) if w]
    joiner = "-" if style == "kebab" else "_"
    return joiner.join(w.lower() for w in words)


def _token_values(scheme: NamingScheme, name: str, number: Optional[int], now: dt.datetime) -> dict[str, str]:
    values = {
        "YYYY": f"{now.year:04d}",
        "YY": f"{now.year % 100:02d}",
        "MM": f"{now.month:02d}",
        "DD": f"{now.day:02d}",
        "name": name,
        "sep": scheme.sep,
    }
    if number is not None:
        values["NN"] = f"{number:0{scheme.pad}d}"
    return values


def render_folder_name(scheme: NamingScheme, name: str, number: Optional[int], now: dt.datetime) -> str:
    """Fill the scheme's pattern in. ``name`` must already be sanitised."""
    values = _token_values(scheme, name, number, now)
    out = []
    for kind, text in scheme.validate():
        out.append(text if kind == "lit" else values[text])
    return "".join(out)


def _counter_regex(scheme: NamingScheme, parts: list[Part]) -> re.Pattern[str]:
    pieces = []
    for kind, text in parts:
        if kind == "lit":
            pieces.append(re.escape(text))
        elif text == "YYYY":
            pieces.append(r"(?P<YYYY>\d{4})")
        elif text == "YY":
            pieces.append(r"(?P<YY>\d{2})")
        elif text in ("MM", "DD"):
            pieces.append(r"\d{2}")
        elif text == "NN":
            pieces.append(r"(?P<NN>\d+)")
        elif text == "name":
            pieces.append(r".+")
        elif text == "sep":
            pieces.append(re.escape(scheme.sep))
    return re.compile("".join(pieces), re.DOTALL)


def next_number(scheme: NamingScheme, existing_names: Iterable[str], now: dt.datetime) -> Optional[int]:
    """Return the next project number, or ``None`` if the pattern has no ``{NN}``.

    Only folders whose names match the scheme's pattern are considered, so unrelated
    folders (``01-Assets``, ``Thumbs``, ...) never inflate the counter.
    """
    parts = scheme.validate()
    if not any(kind == "tok" and text == "NN" for kind, text in parts):
        return None
    regex = _counter_regex(scheme, parts)
    per_year = scheme.counter_scope == "per_year"
    highest = 0
    for existing in existing_names:
        match = regex.fullmatch(existing)
        if not match:
            continue
        groups = match.groupdict()
        if per_year:
            if "YYYY" in groups and groups["YYYY"] is not None and int(groups["YYYY"]) != now.year:
                continue
            if "YY" in groups and groups["YY"] is not None and int(groups["YY"]) != now.year % 100:
                continue
        highest = max(highest, int(groups["NN"]))
    return highest + 1


@dataclass(frozen=True)
class BuiltName:
    folder_name: str
    number: Optional[int]
    name_part: str
    name_adjusted: bool  # True if sanitising changed what the user typed


def build_folder_name(
    scheme: NamingScheme,
    raw_name: str,
    existing_names: Iterable[str],
    now: Optional[dt.datetime] = None,
) -> BuiltName:
    """Turn what the user typed into the final folder name."""
    now = now or dt.datetime.now()
    typed = raw_name.strip()
    if not typed:
        raise InvalidNameError("Please type a project name.")
    sanitized = sanitize_name(typed)
    if not sanitized:
        raise InvalidNameError("The project name only contains characters that are not allowed in folder names.")
    name_part = apply_case(sanitized, scheme.case)
    if not name_part:
        raise InvalidNameError("The project name is empty after applying the case style.")
    number = next_number(scheme, existing_names, now)
    folder_name = render_folder_name(scheme, name_part, number, now)
    validate_component(folder_name)
    return BuiltName(folder_name, number, name_part, sanitized != " ".join(typed.split()))
