import datetime as dt
from pathlib import Path

import pytest

from oneclick.core.errors import UndoError
from oneclick.core.settings import SettingsStore
from oneclick.core.undo import UndoStore
from oneclick.ui.controller import AppController

NOW = dt.datetime(2026, 11, 14, 9, 30)


@pytest.fixture
def make(tmp_path):
    def factory(**kwargs):
        dest = tmp_path / "work"
        dest.mkdir(exist_ok=True)
        return AppController(
            SettingsStore(tmp_path / "cfg" / "settings.json"),
            UndoStore(tmp_path / "cfg" / "undo.json"),
            initial_destination=kwargs.pop("initial_destination", str(dest)),
            clock=lambda: NOW,
            **kwargs,
        )

    return factory


def test_starts_with_motion_video_and_default_scheme(make):
    c = make()
    assert c.template.id == "motion-video" and c.scheme.id == "default"


def test_preview_placeholder_when_no_name(make):
    p = make().preview()
    assert p.is_placeholder and not p.can_create
    assert p.folder_name == "26-01-Project Name"
    assert p.hint == "Type a project name."
    assert p.tree_lines[0] == "26-01-Project Name" and "├─ 01-Assets" in p.tree_lines


def test_preview_with_name_can_create(make):
    c = make()
    c.name = "Brand Film"
    p = c.preview()
    assert p.can_create and p.error is None and p.folder_name == "26-01-Brand Film"


def test_preview_numbers_follow_existing_folders(make, tmp_path):
    c = make()
    (tmp_path / "work" / "26-09-Old").mkdir()
    c.name = "New"
    assert c.preview().folder_name == "26-10-New"


def test_preview_listing_is_cached_until_refreshed(make, tmp_path):
    ticks = iter([0.0, 1.0, 2.0, 100.0, 101.0])
    c = make(monotonic=lambda: next(ticks))
    c.name = "A"
    assert c.preview().folder_name == "26-01-A"  # lists the folder (t=0)
    (tmp_path / "work" / "26-05-X").mkdir()
    assert c.preview().folder_name == "26-01-A"  # cached (t=1)
    c.refresh_listing()
    assert c.preview().folder_name == "26-06-A"  # re-listed (t=2)


def test_preview_reports_bad_destination_but_still_shows_name(make):
    c = make(initial_destination="/definitely/not/here")
    c.name = "X"
    p = c.preview()
    assert not p.can_create and "does not exist" in p.error
    assert p.folder_name == "26-01-X"


def test_preview_empty_destination_gives_hint(make):
    c = make()
    c.destination = "  "
    c.name = "X"
    p = c.preview()
    assert not p.can_create and "Choose where" in p.hint


def test_preview_warns_about_adjusted_characters(make):
    c = make()
    c.name = "a/b"
    p = c.preview()
    assert p.can_create and p.warnings


def test_preview_with_missing_template_folder(make, tmp_path):
    c = make()
    folder = tmp_path / "tpl"
    folder.mkdir()
    c.add_folder_template(str(folder))
    folder.rmdir()
    c.library.reload()
    c.name = "X"
    p = c.preview()
    assert not p.can_create and "not found" in p.error


def test_create_persists_choices_and_enables_undo(make, tmp_path):
    c = make()
    c.name = "Real One"
    c.template_id = "photo"
    c.scheme_id = "year4"
    created = c.create()
    assert created.path == tmp_path / "work" / "2026-01-Real One"
    assert (created.path / "01-Assets" / "02-RAW").is_dir()
    saved = SettingsStore(tmp_path / "cfg" / "settings.json").load()
    assert saved.template_id == "photo" and saved.scheme_id == "year4"
    assert saved.last_destination == str(tmp_path / "work")
    # a fresh controller remembers
    again = make(initial_destination=None)
    assert again.template_id == "photo" and again.scheme_id == "year4"
    assert again.destination == str(tmp_path / "work")
    record, problems = again.undo_info()
    assert record is not None and problems == []


def test_second_create_in_same_destination_increments(make):
    c = make()
    c.name = "One"
    c.create()
    c.name = "Two"
    assert c.preview().folder_name == "26-02-Two"
    assert c.create().folder_name == "26-02-Two"


def test_undo_through_controller(make, tmp_path):
    c = make()
    c.name = "Temp"
    created = c.create()
    assert c.last_record() is not None
    assert c.undo() == created.path and not created.path.exists()
    assert c.last_record() is None
    with pytest.raises(UndoError):
        c.undo()


def test_remember_last_choices_off_uses_default_template(make, tmp_path):
    c = make()
    c.settings.remember_last_choices = False
    c.settings.default_template_id = "music"
    c.settings.template_id = "photo"
    c.store.save(c.settings)
    fresh = make()
    assert fresh.template_id == "music"


def test_reload_library_after_template_removed(make, tmp_path):
    c = make()
    folder = tmp_path / "tpl"
    folder.mkdir()
    t = c.add_folder_template(str(folder))
    assert c.template_id == t.id
    c.library.remove_custom_template(t.id)
    c.reload_library()
    assert c.template_id == "motion-video"
