import datetime as dt
import json
import os
from pathlib import Path

import pytest

from oneclick.core.errors import (
    CreateError,
    DestinationError,
    ProjectExistsError,
    TemplateError,
    UndoError,
)
from oneclick.core.naming import BUILTIN_SCHEMES
from oneclick.core.project import create_project, plan_project
from oneclick.core.templates import Template, load_builtin_templates
from oneclick.core.undo import UndoStore, check_untouched, undo_last

NOW = dt.datetime(2026, 11, 14, 9, 30)
SCHEME = BUILTIN_SCHEMES[0]


@pytest.fixture
def builtins():
    return {t.id: t for t in load_builtin_templates()}


def tree(path: Path) -> set[str]:
    out = set()
    for dirpath, dirnames, filenames in os.walk(path):
        base = Path(dirpath).relative_to(path).as_posix()
        base = "" if base == "." else base + "/"
        out.update(base + d + "/" for d in dirnames)
        out.update(base + f for f in filenames)
    return out


# ---- built-in presets ------------------------------------------------------


def test_all_six_presets_load_in_order(builtins):
    ids = [t.id for t in load_builtin_templates()]
    assert ids == ["motion-video", "photo", "graphic-design", "3d", "web-dev", "music"]


def test_motion_video_matches_the_original_v1_structure(builtins):
    created = {e.rel for e in builtins["motion-video"].entries()}
    assert created == {
        "01-Assets",
        "01-Assets/01-Doc",
        "01-Assets/02-Images & PSDs",
        "01-Assets/03-Vector & Fonts",
        "01-Assets/04-Footages",
        "01-Assets/05-Audio",
        "02-Project Files",
        "02-Project Files/_archive",
        "03-Final Output",
        "03-Final Output/_archive",
    }


def test_every_preset_has_the_three_top_level_folders(builtins):
    for template in builtins.values():
        tops = {e.rel for e in template.entries() if "/" not in e.rel and e.is_dir}
        assert tops == {"01-Assets", "02-Project Files", "03-Final Output"}, template.id


# ---- creating projects -----------------------------------------------------


def test_create_manifest_project(tmp_path, builtins):
    (tmp_path / "26-01-Existing").mkdir()
    plan = plan_project(tmp_path, "Brand Film", builtins["motion-video"], SCHEME, NOW)
    assert plan.folder_name == "26-02-Brand Film"
    result = create_project(plan, now=NOW)
    assert result.path == tmp_path / "26-02-Brand Film"
    assert "01-Assets/02-Images & PSDs/" in tree(result.path)
    assert "03-Final Output/_archive/" in tree(result.path)


def test_placeholders_in_manifest_files(tmp_path, builtins):
    plan = plan_project(tmp_path, "Site", builtins["web-dev"], SCHEME, NOW)
    result = create_project(plan, now=NOW)
    readme = (result.path / "README.md").read_text(encoding="utf-8")
    assert "# 26-01-Site" in readme and "2026-11-14" in readme and "{{" not in readme


def test_existing_project_is_never_overwritten(tmp_path, builtins):
    plan = plan_project(tmp_path, "Dup", builtins["photo"], SCHEME, NOW)
    create_project(plan, now=NOW)
    with pytest.raises(ProjectExistsError):
        create_project(plan, now=NOW)  # same plan again: folder is there now


def test_plan_detects_existing_target_case_insensitively(tmp_path, builtins):
    # counter is bypassed with a pattern without {NN} so the same name is generated twice
    from oneclick.core.naming import NamingScheme

    scheme = NamingScheme("x", "x", pattern="{name}")
    (tmp_path / "SHOOT").mkdir()
    with pytest.raises(ProjectExistsError):
        plan_project(tmp_path, "shoot", builtins["photo"], scheme, NOW)


def test_bad_destinations(tmp_path, builtins):
    with pytest.raises(DestinationError):
        plan_project(tmp_path / "missing", "X", builtins["photo"], SCHEME, NOW)
    afile = tmp_path / "file.txt"
    afile.write_text("hi")
    with pytest.raises(DestinationError):
        plan_project(afile, "X", builtins["photo"], SCHEME, NOW)


def test_long_path_warning(tmp_path, builtins):
    deep = tmp_path
    for _ in range(4):
        deep = deep / ("d" * 40)
    deep.mkdir(parents=True)
    plan = plan_project(deep, "x" * 60, builtins["motion-video"], SCHEME, NOW)
    assert any("characters" in w for w in plan.warnings)


# ---- folder templates ------------------------------------------------------


@pytest.fixture
def folder_template(tmp_path):
    src = tmp_path / "MyTemplate"
    (src / "Footage" / "Raw").mkdir(parents=True)
    (src / "Exports").mkdir()
    (src / "Footage" / "notes.txt").write_text("hello")
    (src / ".DS_Store").write_text("junk")
    (src / "Thumbs.db").write_text("junk")
    (src / "template.json").write_text(json.dumps({"name": "Nice Name", "description": "d"}))
    return src


def test_folder_template_reads_manifest_name(folder_template):
    t = Template.from_folder(folder_template)
    assert t.name == "Nice Name" and t.description == "d"


def test_folder_template_copy_ignores_junk_and_manifest(tmp_path, folder_template):
    dest = tmp_path / "out"
    dest.mkdir()
    t = Template.from_folder(folder_template)
    plan = plan_project(dest, "Job", t, SCHEME, NOW)
    result = create_project(plan, now=NOW)
    assert tree(result.path) == {"Footage/", "Footage/Raw/", "Footage/notes.txt", "Exports/"}
    assert (result.path / "Footage" / "notes.txt").read_text() == "hello"


def test_destination_inside_template_is_refused(folder_template):
    t = Template.from_folder(folder_template)
    with pytest.raises(DestinationError):
        plan_project(folder_template / "Exports", "Loop", t, SCHEME, NOW)


def test_missing_folder_template_is_unavailable(tmp_path):
    t = Template.from_folder(tmp_path / "gone")
    assert not t.available
    with pytest.raises(TemplateError):
        plan_project(tmp_path, "X", t, SCHEME, NOW)


def test_oversized_folder_template_rejected(tmp_path, monkeypatch):
    import oneclick.core.templates as tm

    monkeypatch.setattr(tm, "MAX_TEMPLATE_ENTRIES", 5)
    src = tmp_path / "big"
    src.mkdir()
    for i in range(10):
        (src / f"d{i}").mkdir()
    t = Template.from_folder(src)
    assert "too big" in (t.problem() or "")


def test_symlinks_are_skipped(tmp_path, folder_template):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x")
    try:
        os.symlink(outside, folder_template / "link")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    t = Template.from_folder(folder_template)
    assert not any(e.rel.startswith("link") for e in t.entries())


# ---- manifest validation ---------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "Bad Id", "name": "x"},
        {"id": "ok", "name": ""},
        {"id": "ok", "name": "x", "folders": ["../escape"]},
        {"id": "ok", "name": "x", "folders": ["/abs"]},
        {"id": "ok", "name": "x", "folders": ["C:/win"]},
        {"id": "ok", "name": "x", "folders": ["a\\b"]},
        {"id": "ok", "name": "x", "folders": ["con"]},
        {"id": "ok", "name": "x", "files": {"a.txt": 5}},
        {"id": "ok", "name": "x", "folders": "notalist"},
    ],
)
def test_bad_manifests_rejected(bad):
    with pytest.raises(TemplateError):
        Template.from_manifest(bad)


# ---- rollback --------------------------------------------------------------


def test_failed_creation_rolls_back(tmp_path, builtins, monkeypatch):
    plan = plan_project(tmp_path, "Boom", builtins["motion-video"], SCHEME, NOW)
    original = Path.mkdir
    calls = {"n": 0}

    def flaky(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == 5:  # fail part-way through the template, after the project folder exists
            raise OSError("disk full")
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "mkdir", flaky)
    with pytest.raises(CreateError):
        create_project(plan, now=NOW)
    monkeypatch.undo()
    assert not plan.project_path.exists()


# ---- undo ------------------------------------------------------------------


def test_undo_removes_untouched_project(tmp_path, builtins):
    store = UndoStore(tmp_path / "cfg" / "undo.json")
    dest = tmp_path / "work"
    dest.mkdir()
    plan = plan_project(dest, "Oops", builtins["web-dev"], SCHEME, NOW)
    result = create_project(plan, undo_store=store, now=NOW)
    assert result.path.exists()
    removed = undo_last(store)
    assert removed == result.path and not result.path.exists()
    assert dest.exists()
    assert store.load() is None


def test_undo_refuses_when_user_added_files(tmp_path, builtins):
    store = UndoStore(tmp_path / "undo.json")
    dest = tmp_path / "work"
    dest.mkdir()
    result = create_project(plan_project(dest, "Keep", builtins["photo"], SCHEME, NOW), undo_store=store, now=NOW)
    (result.path / "01-Assets" / "important.psd").write_text("work")
    with pytest.raises(UndoError) as info:
        undo_last(store)
    assert "added" in str(info.value)
    assert (result.path / "01-Assets" / "important.psd").exists()


def test_undo_refuses_when_template_file_was_edited(tmp_path, builtins):
    store = UndoStore(tmp_path / "undo.json")
    dest = tmp_path / "work"
    dest.mkdir()
    result = create_project(plan_project(dest, "Edit", builtins["web-dev"], SCHEME, NOW), undo_store=store, now=NOW)
    (result.path / "README.md").write_text("I wrote a lot more in here than the template had")
    problems = check_untouched(store.load())
    assert any("modified" in p for p in problems)


def test_undo_with_nothing_recorded(tmp_path):
    with pytest.raises(UndoError):
        undo_last(UndoStore(tmp_path / "none.json"))


def test_undo_record_survives_corrupt_file(tmp_path):
    f = tmp_path / "undo.json"
    f.write_text("{not json")
    assert UndoStore(f).load() is None
