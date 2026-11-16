"""The logic behind the main window, with no Tkinter in it so it can be tested directly."""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core.errors import DestinationError, OneClickError
from ..core.naming import NamingScheme, build_folder_name
from ..core.project import CreatedProject, check_destination, create_project, list_directory_names, plan_project
from ..core.settings import Library, Settings, SettingsStore
from ..core.templates import Template
from ..core.tree import render_tree
from ..core.undo import UndoRecord, UndoStore, check_untouched, undo_last

PLACEHOLDER_NAME = "Project Name"
LISTING_TTL_SECONDS = 5.0


@dataclass
class Preview:
    folder_name: str
    is_placeholder: bool
    tree_lines: list[str]
    number_info: str = ""  # e.g. "Next number: 13  ·  highest existing: 12"
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None
    hint: Optional[str] = None
    can_create: bool = False


class AppController:
    def __init__(
        self,
        store: SettingsStore,
        undo_store: UndoStore,
        initial_destination: Optional[str] = None,
        initial_name: str = "",
        clock: Callable[[], dt.datetime] = dt.datetime.now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.undo_store = undo_store
        self.settings: Settings = store.load()
        self.library = Library(self.settings)
        self._clock = clock
        self._monotonic = monotonic
        self._listing_cache: Optional[tuple[str, float, list[str]]] = None

        self.destination = initial_destination or self.settings.last_destination or str(Path.home())
        self.name = initial_name
        self.template_id = self._starting_template_id()
        self.scheme_id = self.settings.scheme_id if self.settings.remember_last_choices else "default"
        if self.scheme_id not in {s.id for s in self.library.schemes}:
            self.scheme_id = "default"

    # ---- selection -------------------------------------------------------

    def _starting_template_id(self) -> str:
        wanted = self.settings.template_id if self.settings.remember_last_choices else self.settings.default_template_id
        return self.library.get_template(wanted).id

    @property
    def template(self) -> Template:
        return self.library.get_template(self.template_id)

    @property
    def scheme(self) -> NamingScheme:
        return self.library.get_scheme(self.scheme_id)

    def recent_destinations(self) -> list[str]:
        """Recently used destinations that still exist, most recent first."""
        return [d for d in self.settings.recent_destinations if Path(d).is_dir()]

    def reload_library(self) -> None:
        """Call after Settings changed templates or schemes."""
        self.library.reload()
        if self.template_id not in {t.id for t in self.library.templates}:
            self.template_id = self._starting_template_id()
        if self.scheme_id not in {s.id for s in self.library.schemes}:
            self.scheme_id = "default"
        self.store.save(self.settings)

    def add_folder_template(self, path: str) -> Template:
        template = self.library.add_folder_template(Path(path))
        self.template_id = template.id
        self.store.save(self.settings)
        return template

    # ---- destination listing (cached, because the preview runs on every keystroke) ----

    def _listing(self, destination: Path) -> list[str]:
        key = str(destination)
        now = self._monotonic()
        cached = self._listing_cache
        if cached and cached[0] == key and now - cached[1] < LISTING_TTL_SECONDS:
            return cached[2]
        names = list_directory_names(destination)
        self._listing_cache = (key, now, names)
        return names

    def refresh_listing(self) -> None:
        self._listing_cache = None

    # ---- preview ---------------------------------------------------------

    def preview(self) -> Preview:
        typed = self.name.strip()
        is_placeholder = not typed
        raw = PLACEHOLDER_NAME if is_placeholder else self.name
        template, scheme = self.template, self.scheme
        dest_text = self.destination.strip()

        error: Optional[str] = None
        hint: Optional[str] = None
        warnings: list[str] = []
        folder_name = ""
        plan_ok = False
        number_info = ""

        dest_path: Optional[Path] = None
        existing: list[str] = []
        if not dest_text:
            hint = "Choose where the project should be created."
        else:
            candidate = Path(dest_text).expanduser()
            try:
                check_destination(candidate)
                existing = self._listing(candidate)
                dest_path = candidate
            except DestinationError as problem:
                error = str(problem)

        if dest_path is not None:
            try:
                plan = plan_project(dest_path, raw, template, scheme, self._clock(), existing_names=existing)
                folder_name, warnings, plan_ok = plan.folder_name, list(plan.warnings), True
                if plan.number is not None:
                    highest = plan.number - 1
                    number_info = f"Next number: {plan.number}" + (f"  ·  highest existing: {highest}" if highest else "  ·  first project in this folder")
            except OneClickError as problem:
                error = str(problem)

        if not folder_name:  # still show what the name would look like
            try:
                folder_name = build_folder_name(scheme, raw, existing, self._clock()).folder_name
            except OneClickError as problem:
                error = error or str(problem)

        try:
            tree_lines = render_tree(folder_name or "…", template.entries())
        except OneClickError as problem:
            tree_lines = [folder_name or "…"]
            error = error or str(problem)

        if is_placeholder and plan_ok:
            hint = "Type a project name."
        return Preview(
            folder_name=folder_name,
            is_placeholder=is_placeholder,
            tree_lines=tree_lines,
            number_info=number_info,
            warnings=warnings,
            error=error,
            hint=hint,
            can_create=plan_ok and not is_placeholder,
        )

    # ---- actions ---------------------------------------------------------

    def create(self) -> CreatedProject:
        """Create the project and remember the choices. Raises :class:`OneClickError`."""
        dest = Path(self.destination.strip()).expanduser()
        plan = plan_project(dest, self.name, self.template, self.scheme, self._clock())
        created = create_project(plan, undo_store=self.undo_store, now=self._clock())
        self.settings.remember_destination(str(dest))
        self.settings.template_id = self.template_id
        self.settings.scheme_id = self.scheme_id
        self.store.save(self.settings)
        self.refresh_listing()
        return created

    def last_record(self) -> Optional[UndoRecord]:
        """Cheap check (reads one small file) used to enable the Undo button."""
        return self.undo_store.load()

    def undo_info(self) -> tuple[Optional[UndoRecord], list[str]]:
        """The last-created project and any reasons it can't be undone (empty list = can undo)."""
        record = self.undo_store.load()
        if record is None:
            return None, []
        return record, check_untouched(record)

    def undo(self) -> Path:
        removed = undo_last(self.undo_store)
        self.refresh_listing()
        return removed
