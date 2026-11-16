"""User settings, stored as human-editable JSON, and the template/scheme library built from them."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .errors import InvalidPatternError, TemplateError
from .naming import BUILTIN_SCHEMES, NamingScheme
from .templates import DEFAULT_TEMPLATE_ID, Template, load_builtin_templates

log = logging.getLogger("oneclick")

SETTINGS_VERSION = 2
DEFAULT_SCHEME_ID = "default"
MAX_RECENT_DESTINATIONS = 8


@dataclass
class CustomTemplateRecord:
    """A template that is a real folder on disk."""

    id: str
    name: str
    path: str


@dataclass
class Settings:
    version: int = SETTINGS_VERSION
    last_destination: str = ""
    recent_destinations: list[str] = field(default_factory=list)
    template_id: str = DEFAULT_TEMPLATE_ID  # last used
    scheme_id: str = DEFAULT_SCHEME_ID  # last used
    default_template_id: str = DEFAULT_TEMPLATE_ID
    remember_last_choices: bool = True
    open_after_create: bool = True
    close_after_create: bool = True
    dark_mode: bool = True
    user_schemes: list[NamingScheme] = field(default_factory=list)
    custom_templates: list[CustomTemplateRecord] = field(default_factory=list)
    user_templates: list[dict[str, Any]] = field(default_factory=list)  # editable manifests (same shape as presets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "last_destination": self.last_destination,
            "recent_destinations": list(self.recent_destinations),
            "template_id": self.template_id,
            "scheme_id": self.scheme_id,
            "default_template_id": self.default_template_id,
            "remember_last_choices": self.remember_last_choices,
            "open_after_create": self.open_after_create,
            "close_after_create": self.close_after_create,
            "dark_mode": self.dark_mode,
            "user_schemes": [s.to_dict() for s in self.user_schemes],
            "custom_templates": [{"id": t.id, "name": t.name, "path": t.path} for t in self.custom_templates],
            "user_templates": [dict(t) for t in self.user_templates],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        base = cls()

        def text(key: str, default: str) -> str:
            value = data.get(key, default)
            return value if isinstance(value, str) else default

        def flag(key: str, default: bool) -> bool:
            value = data.get(key, default)
            return value if isinstance(value, bool) else default

        def items(key: str) -> list:
            value = data.get(key, [])
            return value if isinstance(value, list) else []

        schemes: list[NamingScheme] = []
        for item in items("user_schemes"):
            if not isinstance(item, dict):
                continue
            scheme = NamingScheme.from_dict(item)
            try:
                scheme.validate()
            except InvalidPatternError:
                log.warning("Dropping invalid saved naming scheme %r", scheme.id)
                continue
            if scheme.id and scheme.id not in {b.id for b in BUILTIN_SCHEMES}:
                schemes.append(scheme)

        customs: list[CustomTemplateRecord] = []
        for item in items("custom_templates"):
            if isinstance(item, dict) and all(isinstance(item.get(k), str) and item.get(k) for k in ("id", "name", "path")):
                customs.append(CustomTemplateRecord(item["id"], item["name"], item["path"]))

        user_templates: list[dict[str, Any]] = []
        for item in items("user_templates"):
            if not isinstance(item, dict):
                continue
            try:
                Template.from_manifest(item)  # validate; keep the raw dict so unknown keys survive
            except TemplateError as problem:
                log.warning("Dropping invalid saved template: %s", problem)
                continue
            user_templates.append(item)

        recent = [d for d in items("recent_destinations") if isinstance(d, str) and d][:MAX_RECENT_DESTINATIONS]

        return cls(
            version=SETTINGS_VERSION,
            last_destination=text("last_destination", base.last_destination),
            recent_destinations=recent,
            template_id=text("template_id", base.template_id),
            scheme_id=text("scheme_id", base.scheme_id),
            default_template_id=text("default_template_id", base.default_template_id),
            remember_last_choices=flag("remember_last_choices", base.remember_last_choices),
            open_after_create=flag("open_after_create", base.open_after_create),
            close_after_create=flag("close_after_create", base.close_after_create),
            dark_mode=flag("dark_mode", base.dark_mode),
            user_schemes=schemes,
            custom_templates=customs,
            user_templates=user_templates,
        )

    def remember_destination(self, destination: str) -> None:
        self.last_destination = destination
        self.recent_destinations = [destination] + [d for d in self.recent_destinations if d != destination]
        del self.recent_destinations[MAX_RECENT_DESTINATIONS:]


class SettingsStore:
    """Loads and saves :class:`Settings`. A corrupt file is set aside, never crashes the app."""

    def __init__(self, file: Path) -> None:
        self.file = Path(file)

    def load(self) -> Settings:
        try:
            raw = self.file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Settings()
        except OSError:
            log.exception("Could not read settings; using defaults")
            return Settings()
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("settings root is not an object")
            return Settings.from_dict(data)
        except ValueError:
            backup = self.file.with_suffix(".bad.json")
            log.warning("Settings file is corrupt; moving it to %s and using defaults", backup)
            try:
                os.replace(self.file, backup)
            except OSError:
                pass
            return Settings()

    def save(self, settings: Settings) -> None:
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
            os.replace(tmp, self.file)
        except OSError:
            log.exception("Could not save settings")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class Library:
    """All templates and naming schemes available right now (built-in plus the user's)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._builtin_templates = load_builtin_templates()
        self.reload()

    def reload(self) -> None:
        user = [Template.from_manifest(data) for data in self.settings.user_templates]
        customs = [
            Template.from_folder(Path(rec.path), template_id=rec.id, name=rec.name)
            for rec in self.settings.custom_templates
        ]
        self.templates: list[Template] = self._builtin_templates + user + customs
        self.schemes: list[NamingScheme] = list(BUILTIN_SCHEMES) + list(self.settings.user_schemes)

    # ---- lookups -----------------------------------------------------------

    def get_template(self, template_id: str) -> Template:
        for template in self.templates:
            if template.id == template_id:
                return template
        for template in self.templates:
            if template.id == DEFAULT_TEMPLATE_ID:
                return template
        return self.templates[0]

    def get_scheme(self, scheme_id: str) -> NamingScheme:
        for scheme in self.schemes:
            if scheme.id == scheme_id:
                return scheme
        return self.schemes[0]

    def _unique_template_id(self, base: str) -> str:
        base = _slug(base) or "template"
        existing = {t.id for t in self.templates}
        candidate, n = base, 2
        while candidate in existing:
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    def unique_template_name(self, wanted: str) -> str:
        """``wanted`` itself if free, otherwise ``wanted (2)``, ``wanted (3)``..."""
        names = {t.name.casefold() for t in self.templates}
        if wanted.casefold() not in names:
            return wanted
        n = 2
        while f"{wanted} ({n})".casefold() in names:
            n += 1
        return f"{wanted} ({n})"

    # ---- folder templates ----------------------------------------------------

    def add_folder_template(self, path: Path) -> Template:
        """Register ``path`` as a custom template (or return the existing entry for it)."""
        path = Path(path)
        if not path.is_dir():
            raise TemplateError(f"'{path}' is not a folder.")
        template = Template.from_folder(path)
        for record in self.settings.custom_templates:
            if record.id == template.id:
                self.reload()
                return self.get_template(record.id)
        self.settings.custom_templates.append(CustomTemplateRecord(template.id, template.name, str(path)))
        self.reload()
        return self.get_template(template.id)

    def remove_template(self, template_id: str) -> None:
        """Remove a user-made or folder template (built-ins can't be removed). Nothing on disk is touched."""
        self.settings.custom_templates = [t for t in self.settings.custom_templates if t.id != template_id]
        self.settings.user_templates = [t for t in self.settings.user_templates if t.get("id") != template_id]
        if self.settings.template_id == template_id:
            self.settings.template_id = DEFAULT_TEMPLATE_ID
        if self.settings.default_template_id == template_id:
            self.settings.default_template_id = DEFAULT_TEMPLATE_ID
        self.reload()

    remove_custom_template = remove_template  # backwards-compatible name

    # ---- editable (manifest) templates ------------------------------------------

    def save_user_template(self, template_id: Optional[str], name: str, folders: list[str], files: Optional[dict[str, str]] = None, description: str = "") -> Template:
        """Create (``template_id`` None) or update an editable template. Returns the saved template."""
        name = name.strip()
        if not name:
            raise TemplateError("Please give the template a name.")
        if template_id is None:
            template_id = self._unique_template_id(name)
        elif any(t.id == template_id and (t.builtin or t.is_folder_template) for t in self.templates):
            raise TemplateError("Built-in and folder templates can't be edited directly. Duplicate it first.")
        clash = next((t for t in self.templates if t.name.casefold() == name.casefold() and t.id != template_id), None)
        if clash is not None:
            raise TemplateError(f"A template named '{clash.name}' already exists. Choose another name.")
        existing = next((t for t in self.settings.user_templates if t.get("id") == template_id), None)
        data: dict[str, Any] = dict(existing or {})
        data.update({"id": template_id, "name": name, "folders": list(folders), "description": description})
        if files is not None:
            data["files"] = dict(files)
        Template.from_manifest(data)  # validates folder names
        self.settings.user_templates = [t for t in self.settings.user_templates if t.get("id") != template_id] + [data]
        self.reload()
        return self.get_template(template_id)

    def duplicate_template(self, template_id: str, new_name: Optional[str] = None) -> Template:
        """Copy any template (built-in, user-made or folder) into a new editable template.

        For a folder template only its folder structure is copied; files inside it are not.
        """
        source = self.get_template(template_id)
        folders = [e.rel for e in source.entries() if e.is_dir]
        files = dict(source.files) if not source.is_folder_template else {}
        name = new_name.strip() if new_name else self.unique_template_name(f"{source.name} copy")
        return self.save_user_template(None, name, folders, files, source.description)

    def rename_template(self, template_id: str, new_name: str) -> Template:
        template = self.get_template(template_id)
        if template.builtin:
            raise TemplateError("Built-in templates can't be renamed. Duplicate it to make your own copy.")
        new_name = new_name.strip()
        if not new_name:
            raise TemplateError("Please give the template a name.")
        if template.is_folder_template:
            for record in self.settings.custom_templates:
                if record.id == template_id:
                    record.name = new_name
            self.reload()
            return self.get_template(template_id)
        return self.save_user_template(template_id, new_name, list(template.folders), dict(template.files), template.description)

    # ---- naming schemes ---------------------------------------------------------

    def save_scheme(self, scheme: NamingScheme) -> NamingScheme:
        """Add or update a user scheme. Built-in schemes can't be overwritten."""
        scheme.validate()
        if any(b.id == scheme.id for b in BUILTIN_SCHEMES):
            raise InvalidPatternError("Built-in naming schemes can't be changed. Save it under a new name.")
        if not scheme.label.strip():
            raise InvalidPatternError("Please give the naming scheme a name.")
        self.settings.user_schemes = [s for s in self.settings.user_schemes if s.id != scheme.id] + [scheme]
        self.reload()
        return self.get_scheme(scheme.id)

    def new_scheme_id(self, label: str) -> str:
        slug = _slug(label) or "scheme"
        existing = {s.id for s in self.schemes}
        candidate, n = slug, 2
        while candidate in existing:
            candidate, n = f"{slug}-{n}", n + 1
        return candidate

    def delete_scheme(self, scheme_id: str) -> None:
        self.settings.user_schemes = [s for s in self.settings.user_schemes if s.id != scheme_id]
        if self.settings.scheme_id == scheme_id:
            self.settings.scheme_id = DEFAULT_SCHEME_ID
        self.reload()
