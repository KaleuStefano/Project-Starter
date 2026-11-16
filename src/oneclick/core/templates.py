"""Templates: the folder structures a new project is built from.

Two kinds exist:

* **Manifest templates** (the built-in presets): a list of folders and optional small
  text files, described in JSON. Text files may use ``{{project_name}}``,
  ``{{folder_name}}``, ``{{number}}``, ``{{year}}`` and ``{{date}}``.
* **Folder templates**: any real folder on disk. Its contents are copied as-is.
  An optional ``template.json`` at its top level may set ``name`` and ``description``
  and is never copied.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from .errors import TemplateError
from .models import CreatedEntry, TemplateEntry
from .sanitize import ILLEGAL_CHARS, validate_component

DEFAULT_TEMPLATE_ID = "motion-video"
IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini", ".git"})
MANIFEST_NAME = "template.json"
MAX_TEMPLATE_ENTRIES = 2000
MAX_TEMPLATE_BYTES = 200 * 1024 * 1024
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _validate_rel_path(rel: str, what: str) -> str:
    """Check a manifest path is relative, forward-slash separated and made of valid names."""
    if not isinstance(rel, str) or not rel.strip():
        raise TemplateError(f"Template {what} must be a non-empty text path.")
    if "\\" in rel or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        raise TemplateError(f"Template {what} '{rel}' must be a relative path using '/' separators.")
    parts = PurePosixPath(rel).parts
    for part in parts:
        if part in (".", ".."):
            raise TemplateError(f"Template {what} '{rel}' must not contain '.' or '..'.")
        try:
            validate_component(part)
        except Exception as error:  # InvalidNameError -> TemplateError with context
            raise TemplateError(f"Template {what} '{rel}': {error}") from error
    return "/".join(parts)


@dataclass
class Template:
    id: str
    name: str
    description: str = ""
    folders: tuple[str, ...] = ()
    files: dict[str, str] = field(default_factory=dict)
    source: Optional[Path] = None  # set for folder templates
    builtin: bool = False
    order: int = 100
    available: bool = True
    _scan: Optional[tuple[list[TemplateEntry], int, bool]] = field(default=None, repr=False, compare=False)

    # ---- construction -------------------------------------------------

    @classmethod
    def from_manifest(cls, data: dict[str, Any], builtin: bool = False) -> "Template":
        template_id = str(data.get("id", ""))
        if not _ID_RE.match(template_id):
            raise TemplateError(f"Template id '{template_id}' is invalid (use lowercase letters, digits, - or _).")
        name = str(data.get("name", "")).strip()
        if not name:
            raise TemplateError(f"Template '{template_id}' has no name.")
        folders = data.get("folders", [])
        files = data.get("files", {})
        if not isinstance(folders, list) or not isinstance(files, dict):
            raise TemplateError(f"Template '{template_id}': 'folders' must be a list and 'files' an object.")
        clean_folders = tuple(_validate_rel_path(f, "folder") for f in folders)
        clean_files: dict[str, str] = {}
        for rel, content in files.items():
            if not isinstance(content, str):
                raise TemplateError(f"Template '{template_id}': file '{rel}' content must be text.")
            clean_files[_validate_rel_path(rel, "file")] = content
        return cls(
            id=template_id,
            name=name,
            description=str(data.get("description", "")),
            folders=clean_folders,
            files=clean_files,
            builtin=builtin,
            order=int(data.get("order", 100)),
        )

    @classmethod
    def from_folder(cls, path: Path, template_id: Optional[str] = None, name: Optional[str] = None) -> "Template":
        """Use a real folder as a template. Missing folders yield an unavailable template."""
        path = Path(path)
        if template_id is None:
            digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:8]
            template_id = f"folder-{digest}"
        display = name or path.name or str(path)
        description = ""
        if not path.is_dir():
            return cls(
                id=template_id,
                name=display,
                description="Folder not found",
                source=path,
                available=False,
            )
        manifest = path / MANIFEST_NAME
        if manifest.is_file():
            try:
                meta = json.loads(manifest.read_text(encoding="utf-8"))
                if isinstance(meta, dict):
                    display = name or str(meta.get("name") or display)
                    description = str(meta.get("description", ""))
            except (OSError, ValueError):
                pass  # a broken template.json should not make the folder unusable
        return cls(id=template_id, name=display, description=description, source=path)

    # ---- inspection ----------------------------------------------------

    @property
    def is_folder_template(self) -> bool:
        return self.source is not None

    def _scan_source(self) -> tuple[list[TemplateEntry], int, bool]:
        assert self.source is not None
        entries: list[TemplateEntry] = []
        total = 0
        truncated = False
        root = self.source
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            current = Path(dirpath)
            dirnames[:] = sorted(
                d for d in dirnames if d not in IGNORED_NAMES and not (current / d).is_symlink()
            )
            rel_dir = current.relative_to(root).as_posix()
            prefix = "" if rel_dir == "." else rel_dir + "/"
            for d in dirnames:
                entries.append(TemplateEntry(prefix + d, True))
            for f in sorted(filenames):
                if f in IGNORED_NAMES or (current / f).is_symlink() or (prefix == "" and f == MANIFEST_NAME):
                    continue
                try:
                    size = (current / f).stat().st_size
                except OSError:
                    size = 0
                total += size
                entries.append(TemplateEntry(prefix + f, False, size))
            if len(entries) > MAX_TEMPLATE_ENTRIES:
                truncated = True
                break
        return entries, total, truncated

    def _manifest_entries(self) -> list[TemplateEntry]:
        dirs: set[str] = set()
        for folder in self.folders:
            parts = folder.split("/")
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        files = dict(self.files)
        for rel in files:
            parts = rel.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        entries = [TemplateEntry(d, True) for d in sorted(dirs)]
        entries += [TemplateEntry(rel, False, len(text.encode("utf-8"))) for rel, text in sorted(files.items())]
        return entries

    def entries(self) -> list[TemplateEntry]:
        """Everything this template creates (cached for the lifetime of the object)."""
        problem = self.problem()
        if problem:
            raise TemplateError(problem)
        if self.source is None:
            return self._manifest_entries()
        return list(self._scan_cached()[0])

    def _scan_cached(self) -> tuple[list[TemplateEntry], int, bool]:
        if self._scan is None:
            self._scan = self._scan_source()
        return self._scan

    def problem(self) -> Optional[str]:
        """Return a user-facing reason this template cannot be used, or ``None``."""
        if not self.available or (self.source is not None and not self.source.is_dir()):
            return f"The template folder '{self.name}' was not found. Check that the drive is connected."
        if self.source is not None:
            entries, total, truncated = self._scan_cached()
            if truncated or len(entries) > MAX_TEMPLATE_ENTRIES:
                return f"The template folder '{self.name}' has more than {MAX_TEMPLATE_ENTRIES} items; it looks too big to be a template."
            if total > MAX_TEMPLATE_BYTES:
                return f"The template folder '{self.name}' is larger than {MAX_TEMPLATE_BYTES // (1024 * 1024)} MB."
        return None

    def longest_relative_path(self) -> int:
        entries = self.entries()
        return max((len(e.rel) for e in entries), default=0)

    # ---- creation ------------------------------------------------------

    def materialize(self, project_path: Path, context: dict[str, str], created: list[CreatedEntry]) -> None:
        """Create this template's contents inside the (already created) ``project_path``.

        Every item is appended to ``created`` immediately after it is made, so a caller can
        roll back precisely if something fails part-way.
        """
        if self.source is None:
            self._materialize_manifest(project_path, context, created)
        else:
            self._materialize_folder(project_path, created)

    def _materialize_manifest(self, project_path: Path, context: dict[str, str], created: list[CreatedEntry]) -> None:
        for entry in self._manifest_entries():
            target = project_path.joinpath(*entry.rel.split("/"))
            if entry.is_dir:
                target.mkdir(exist_ok=True)
                created.append(CreatedEntry(entry.rel, True))
            else:
                text = self.files[entry.rel]
                for key, value in context.items():
                    text = text.replace("{{" + key + "}}", value)
                target.write_text(text, encoding="utf-8", newline="\n")
                created.append(CreatedEntry(entry.rel, False, target.stat().st_size))

    def _materialize_folder(self, project_path: Path, created: list[CreatedEntry]) -> None:
        entries, _, _ = self._scan_cached()
        assert self.source is not None
        # Directories come before the files inside them because os.walk lists a folder's
        # subfolders before moving on, but make it explicit to be safe.
        for entry in sorted(entries, key=lambda e: (not e.is_dir, e.rel.count("/"))):
            src = self.source.joinpath(*entry.rel.split("/"))
            dst = project_path.joinpath(*entry.rel.split("/"))
            if entry.is_dir:
                dst.mkdir(parents=True, exist_ok=True)
                created.append(CreatedEntry(entry.rel, True))
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                created.append(CreatedEntry(entry.rel, False, dst.stat().st_size))


def _builtin_templates_dir() -> Path:
    """Folder holding the preset manifests, both when run from source and inside a PyInstaller app."""
    candidates = [Path(__file__).resolve().parents[1] / "builtin_templates"]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "oneclick" / "builtin_templates")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise TemplateError("The built-in templates are missing from this installation. Please reinstall the app.")


def load_builtin_templates() -> list[Template]:
    """Load the presets shipped inside the app, in display order."""
    templates: list[Template] = []
    for item in sorted(_builtin_templates_dir().glob("*.json")):
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
            templates.append(Template.from_manifest(data, builtin=True))
        except (ValueError, TemplateError) as error:
            raise TemplateError(f"Built-in template '{item.name}' is broken: {error}") from error
    if not templates:
        raise TemplateError("No built-in templates were found. Please reinstall the app.")
    templates.sort(key=lambda t: (t.order, t.name.casefold()))
    return templates
