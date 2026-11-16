import pytest

from oneclick.core.errors import TemplateError
from oneclick.core.settings import Library, Settings, SettingsStore


@pytest.fixture
def lib():
    return Library(Settings())


def test_duplicate_builtin_becomes_editable_copy(lib):
    copy = lib.duplicate_template("motion-video")
    assert copy.name == "Motion / Video copy" and not copy.builtin and not copy.is_folder_template
    assert copy.id == "motion-video-copy"
    assert {e.rel for e in copy.entries()} == {e.rel for e in lib.get_template("motion-video").entries()}
    second = lib.duplicate_template("motion-video")
    assert second.name == "Motion / Video copy (2)" and second.id == "motion-video-copy-2"


def test_duplicate_folder_template_keeps_structure_only(lib, tmp_path):
    src = tmp_path / "Mine"
    (src / "Shots" / "Raw").mkdir(parents=True)
    (src / "Shots" / "note.txt").write_text("x")
    t = lib.add_folder_template(src)
    copy = lib.duplicate_template(t.id, "Editable Mine")
    assert copy.folders == ("Shots", "Shots/Raw") and copy.files == {}


def test_edit_user_template_folders(lib):
    copy = lib.duplicate_template("photo")
    saved = lib.save_user_template(copy.id, "Photo Pro", ["01-RAW", "01-RAW/Day 1", "02-Edits"])
    assert saved.name == "Photo Pro" and saved.folders == ("01-RAW", "01-RAW/Day 1", "02-Edits")
    assert lib.get_template(copy.id).name == "Photo Pro"
    assert [t["name"] for t in lib.settings.user_templates] == ["Photo Pro"]


def test_cannot_edit_or_rename_builtin(lib):
    with pytest.raises(TemplateError):
        lib.save_user_template("motion-video", "Hack", ["x"])
    with pytest.raises(TemplateError):
        lib.rename_template("motion-video", "Hack")


def test_rename_user_and_folder_templates(lib, tmp_path):
    copy = lib.duplicate_template("3d")
    assert lib.rename_template(copy.id, "Blender Jobs").name == "Blender Jobs"
    folder = tmp_path / "F"
    folder.mkdir()
    f = lib.add_folder_template(folder)
    assert lib.rename_template(f.id, "My Folder Tpl").name == "My Folder Tpl"
    assert lib.settings.custom_templates[0].name == "My Folder Tpl"


def test_name_clash_and_bad_folder_names_rejected(lib):
    with pytest.raises(TemplateError):
        lib.save_user_template(None, "Photo", ["a"])  # clashes with the built-in
    with pytest.raises(TemplateError):
        lib.save_user_template(None, "Bad", ["a/../b"])
    with pytest.raises(TemplateError):
        lib.save_user_template(None, "Bad", ["con"])
    with pytest.raises(TemplateError):
        lib.save_user_template(None, "   ", ["a"])


def test_remove_user_template_and_persistence(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    lib = Library(store.load())
    copy = lib.duplicate_template("music")
    lib.settings.default_template_id = copy.id
    store.save(lib.settings)

    reloaded = Library(store.load())
    assert reloaded.get_template(copy.id).name == "Music copy"
    reloaded.remove_template(copy.id)
    assert reloaded.settings.default_template_id == "motion-video"
    assert copy.id not in {t.id for t in reloaded.templates}


def test_invalid_saved_user_template_is_dropped(tmp_path):
    f = tmp_path / "s.json"
    f.write_text('{"user_templates": [{"id": "ok", "name": "Ok", "folders": ["a"]}, {"id": "BAD ID", "name": "x"}]}')
    s = SettingsStore(f).load()
    assert [t["id"] for t in s.user_templates] == ["ok"]


def test_recent_destinations(tmp_path):
    s = Settings()
    for name in "abcdefghij":
        s.remember_destination(str(tmp_path / name))
    assert len(s.recent_destinations) == 8 and s.recent_destinations[0].endswith("j")
    s.remember_destination(str(tmp_path / "c"))
    assert s.recent_destinations[0].endswith("c") and s.recent_destinations.count(str(tmp_path / "c")) == 1
    assert s.last_destination == str(tmp_path / "c")
