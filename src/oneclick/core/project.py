"""Planning and creating a project folder."""

from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .errors import CreateError, DestinationError, ProjectExistsError, TemplateError
from .models import CreatedEntry
from .naming import NamingScheme, build_folder_name
from .templates import Template
from .undo import UndoStore, make_record, remove_entries

log = logging.getLogger("oneclick")

PATH_WARNING_LENGTH = 240  # Windows' classic limit is 260 characters


@dataclass(frozen=True)
class ProjectPlan:
    destination: Path
    folder_name: str
    project_path: Path
    number: Optional[int]
    template: Template
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CreatedProject:
    path: Path
    folder_name: str
    entries: tuple[CreatedEntry, ...]


def check_destination(destination: Path) -> None:
    """Raise :class:`DestinationError` unless ``destination`` is an existing, writable folder."""
    if not destination.exists():
        raise DestinationError(f"The destination folder does not exist:\n{destination}")
    if not destination.is_dir():
        raise DestinationError(f"The destination is not a folder:\n{destination}")
    if not os.access(destination, os.W_OK | os.X_OK):
        raise DestinationError(f"You don't have permission to create folders in:\n{destination}")


def list_directory_names(destination: Path) -> list[str]:
    """Names of the sub-folders in ``destination`` (files are ignored)."""
    try:
        with os.scandir(destination) as scan:
            return [entry.name for entry in scan if entry.is_dir()]
    except OSError as error:
        raise DestinationError(f"Could not read the destination folder:\n{destination}\n({error})") from error


def plan_project(
    destination: Path,
    raw_name: str,
    template: Template,
    scheme: NamingScheme,
    now: Optional[dt.datetime] = None,
    existing_names: Optional[Iterable[str]] = None,
) -> ProjectPlan:
    """Work out what would be created, without touching the disk.

    ``existing_names`` can be supplied to avoid listing the destination again (the UI caches it).
    """
    destination = Path(destination).expanduser()
    check_destination(destination)
    problem = template.problem()
    if problem:
        raise TemplateError(problem)
    if template.source is not None:
        try:
            destination.resolve().relative_to(template.source.resolve())
        except ValueError:
            pass
        else:
            raise DestinationError(
                "The destination is inside the template folder. Choose a destination outside it, "
                "otherwise the template would be copied into itself."
            )

    names = list(existing_names) if existing_names is not None else list_directory_names(destination)
    built = build_folder_name(scheme, raw_name, names, now)
    project_path = destination / built.folder_name
    if built.folder_name.casefold() in {n.casefold() for n in names} or project_path.exists():
        raise ProjectExistsError(f"A folder named '{built.folder_name}' already exists in this destination.")

    warnings: list[str] = []
    if built.name_adjusted:
        warnings.append("Some characters in the name aren't allowed in folder names and were replaced.")
    total = len(str(project_path)) + 1 + template.longest_relative_path()
    if total >= PATH_WARNING_LENGTH:
        warnings.append(
            f"The longest path in this project will be about {total} characters; "
            "Windows may have trouble above 260. Consider a shorter name or destination."
        )
    return ProjectPlan(destination, built.folder_name, project_path, built.number, template, tuple(warnings))


def create_project(
    plan: ProjectPlan,
    undo_store: Optional[UndoStore] = None,
    now: Optional[dt.datetime] = None,
) -> CreatedProject:
    """Create the folder described by ``plan``. Never overwrites; rolls back on failure."""
    now = now or dt.datetime.now()
    try:
        plan.project_path.mkdir(parents=False, exist_ok=False)
    except FileExistsError as error:
        raise ProjectExistsError(f"A folder named '{plan.folder_name}' already exists in this destination.") from error
    except OSError as error:
        raise CreateError(f"Could not create the project folder:\n{error}") from error

    created: list[CreatedEntry] = []
    context = {
        "project_name": plan.folder_name,
        "folder_name": plan.folder_name,
        "number": "" if plan.number is None else str(plan.number),
        "year": f"{now.year:04d}",
        "date": now.date().isoformat(),
    }
    try:
        plan.template.materialize(plan.project_path, context, created)
    except Exception as error:  # includes OSError from copying; always roll back
        log.exception("Creating '%s' failed; rolling back", plan.folder_name)
        leftovers = remove_entries(plan.project_path, created)
        detail = f"\n(Some items could not be cleaned up: {'; '.join(leftovers)})" if leftovers else ""
        raise CreateError(f"Could not create the project, so nothing was kept:\n{error}{detail}") from error

    if undo_store is not None:
        undo_store.save(make_record(plan.project_path, created, now))
    log.info("Created %s (%d items)", plan.project_path, len(created))
    return CreatedProject(plan.project_path, plan.folder_name, tuple(created))
