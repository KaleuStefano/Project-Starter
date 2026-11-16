import json

import pytest

from oneclick.core.errors import InvalidPatternError, TemplateError
from oneclick.core.naming import NamingScheme
from oneclick.core.settings import Library, Settings, SettingsStore


def test_defaults_when_no_file(tmp_path):
    s = SettingsStore(tmp_path / "settings.json").load()
    assert s.template_id == "motion-video" and s.open_after_create


def test_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    s = Settings(last_destination="D:/Projects", close_after_create=False)
    s.user_schemes.append(NamingScheme("mine", "Mine", pattern="{YYYY}{sep}{name}"))
    store.save(s)
    loaded = store.load()
    assert loaded.last_destination == "D:/Projects" and loaded.close_after_create is False
    assert loaded.user_schemes[0].pattern == "{YYYY}{sep}{name}"


def test_corrupt_file_is_set_aside(tmp_path):
    f = tmp_path / "s.json"
    f.write_text("{{{ nope")
    s = SettingsStore(f).load()
    assert s == Settings()
    assert (tmp_path / "s.bad.json").exists()


def test_wrong_types_fall_back_to_defaults(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"open_after_create": "yes", "template_id": 5, "user_schemes": "x", "custom_templates": [1, {"id": "a"}]}))
    s = SettingsStore(f).load()
    assert s.open_after_create is True and s.template_id == "motion-video"
    assert s.user_schemes == [] and s.custom_templates == []


def test_invalid_saved_scheme_is_dropped(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"user_schemes": [{"id": "bad", "label": "bad", "pattern": "{nope}"}]}))
    assert SettingsStore(f).load().user_schemes == []


def test_library_has_builtins(tmp_path):
    lib = Library(Settings())
    assert [t.id for t in lib.templates][:2] == ["motion-video", "photo"]
    assert lib.get_scheme("default").pattern == "{YY}{sep}{NN}{sep}{name}"
    assert lib.get_template("does-not-exist").id == "motion-video"


def test_add_and_remove_folder_template(tmp_path):
    folder = tmp_path / "Mine"
    (folder / "A").mkdir(parents=True)
    lib = Library(Settings())
    t = lib.add_folder_template(folder)
    assert t.id in {x.id for x in lib.templates} and not t.builtin
    again = lib.add_folder_template(folder)
    assert again.id == t.id and len(lib.settings.custom_templates) == 1
    lib.settings.template_id = t.id
    lib.remove_custom_template(t.id)
    assert lib.settings.template_id == "motion-video"
    assert t.id not in {x.id for x in lib.templates}


def test_add_folder_template_requires_folder(tmp_path):
    with pytest.raises(TemplateError):
        Library(Settings()).add_folder_template(tmp_path / "nope")


def test_missing_custom_template_listed_but_unavailable(tmp_path):
    folder = tmp_path / "Gone"
    folder.mkdir()
    lib = Library(Settings())
    t = lib.add_folder_template(folder)
    folder.rmdir()
    lib.reload()
    assert not lib.get_template(t.id).available


def test_save_scheme_rules():
    lib = Library(Settings())
    saved = lib.save_scheme(NamingScheme("mine", "Mine", pattern="{YY}{MM}{sep}{name}"))
    assert saved in lib.schemes
    with pytest.raises(InvalidPatternError):
        lib.save_scheme(NamingScheme("default", "Hack"))  # built-in id
    with pytest.raises(InvalidPatternError):
        lib.save_scheme(NamingScheme("bad", "Bad", pattern="{zzz}"))
    assert lib.new_scheme_id("My Scheme!") == "my-scheme"
    lib.save_scheme(NamingScheme("my-scheme", "x"))
    assert lib.new_scheme_id("My Scheme!") == "my-scheme-2"
    lib.settings.scheme_id = "mine"
    lib.delete_scheme("mine")
    assert lib.settings.scheme_id == "default"
