"""Exercises the window code against a fake Tk (see fake_tk.py for what this does and does not prove)."""

import datetime as dt
from unittest.mock import MagicMock

import pytest

import fake_tk
from oneclick.core.settings import SettingsStore
from oneclick.core.undo import UndoStore
from oneclick.ui.controller import AppController

NOW = dt.datetime(2026, 11, 14, 9, 30)


@pytest.fixture
def env(tmp_path, monkeypatch):
    handles = fake_tk.install(monkeypatch)
    from oneclick.ui import main_window, settings_dialog, template_editor  # imported against the fake Tk

    dest = tmp_path / "work"
    dest.mkdir()
    controller = AppController(
        SettingsStore(tmp_path / "cfg" / "settings.json"),
        UndoStore(tmp_path / "cfg" / "undo.json"),
        initial_destination=str(dest),
        clock=lambda: NOW,
    )
    monkeypatch.setattr(main_window, "open_folder", MagicMock())
    monkeypatch.setattr(main_window, "center_window", MagicMock())
    monkeypatch.setattr(settings_dialog, "center_window", MagicMock())
    monkeypatch.setattr(template_editor, "center_window", MagicMock())
    root = fake_tk.Widget()
    handles.template_editor = template_editor
    yield handles, main_window, settings_dialog, controller, root, dest
    fake_tk.purge_ui_modules()  # don't leak modules bound to the fake Tk into other tests


def test_window_builds_and_previews(env):
    _, main_window, _, controller, root, _ = env
    win = main_window.MainWindow(root, controller)
    assert "26-01-Project Name" in win.tree_text.content
    assert "01-Assets" in win.tree_text.content
    win.create_btn.state.assert_called_with(["disabled"])  # no name typed yet
    assert win.template_combo["values"][0] == "Motion / Video"
    assert "highest" not in win.number_label.configure.call_args.kwargs["text"]
    assert "first project" in win.number_label.configure.call_args.kwargs["text"]
    assert win.template_combo.current() == 0
    assert win.scheme_combo["values"][0] == "YY-NN-Name"


def test_typing_a_name_enables_create_and_updates_preview(env):
    _, main_window, _, controller, root, _ = env
    win = main_window.MainWindow(root, controller)
    win.name_var.set("Brand Film")
    win.create_btn.state.assert_called_with(["!disabled"])
    assert win.tree_text.content.splitlines()[0] == "26-01-Brand Film"


def test_choosing_template_and_scheme_updates_preview(env):
    _, main_window, _, controller, root, _ = env
    win = main_window.MainWindow(root, controller)
    win.name_var.set("Shoot")
    win.template_combo.current(1)  # Photo
    win._on_template_selected()
    win.scheme_combo.current(1)  # YYYY-NN-Name
    win._on_scheme_selected()
    assert controller.template_id == "photo" and controller.scheme_id == "year4"
    assert win.tree_text.content.splitlines()[0] == "2026-01-Shoot"
    assert "02-RAW" in win.tree_text.content


def test_create_makes_folder_opens_it_and_closes(env):
    handles, main_window, _, controller, root, dest = env
    win = main_window.MainWindow(root, controller)
    win.name_var.set("Brand Film")
    win.create()
    assert (dest / "26-01-Brand Film" / "01-Assets" / "05-Audio").is_dir()
    main_window.open_folder.assert_called_once_with(dest / "26-01-Brand Film")
    root.destroy.assert_called_once()


def test_create_stays_open_when_configured_and_undo_works(env):
    handles, main_window, _, controller, root, dest = env
    controller.settings.close_after_create = False
    controller.settings.open_after_create = False
    win = main_window.MainWindow(root, controller)
    win.name_var.set("Keep Open")
    win.create()
    root.destroy.assert_not_called()
    main_window.open_folder.assert_not_called()
    assert win.name_var.get() == "" and "Created 26-01-Keep Open" in win.status_var.get()
    assert controller.last_record() is not None
    win.undo_last()  # Ctrl+Z path; fake askyesno returns True
    assert not (dest / "26-01-Keep Open").exists()
    assert "Removed" in win.status_var.get()


def test_create_does_nothing_without_name(env):
    _, main_window, _, controller, root, dest = env
    win = main_window.MainWindow(root, controller)
    win.create()
    assert list(dest.iterdir()) == []
    root.destroy.assert_not_called()


def test_bad_destination_shows_error_message(env):
    _, main_window, _, controller, root, _ = env
    win = main_window.MainWindow(root, controller)
    win.name_var.set("X")
    win.dest_var.set("/no/such/folder")
    last = win.message_label.configure.call_args.kwargs
    assert "does not exist" in last["text"] and last["style"] == "Error.TLabel"
    win.create_btn.state.assert_called_with(["disabled"])


def test_use_a_folder_registers_custom_template(env, tmp_path):
    handles, main_window, _, controller, root, _ = env
    folder = tmp_path / "MyStructure"
    (folder / "Shots").mkdir(parents=True)
    handles.filedialog.askdirectory.return_value = str(folder)
    win = main_window.MainWindow(root, controller)
    win.add_folder_template()
    assert controller.template.name == "MyStructure"
    assert win.template_combo["values"][-1] == "MyStructure (folder)"
    win.name_var.set("Job")
    assert "Shots" in win.tree_text.content


def test_settings_dialog_builds_and_saves_a_scheme(env):
    handles, main_window, settings_dialog, controller, root, _ = env
    closed = MagicMock()
    dialog = settings_dialog.SettingsDialog(root, controller, start_tab="Naming", on_close=closed)
    assert dialog.template_list.rows[0].startswith("Motion / Video")
    assert "[default]" in dialog.template_list.rows[0]
    assert dialog.s_example.get().startswith("Example:  26-05-My Project")

    dialog.s_label.set("Compact")
    dialog.s_pattern.set("{YY}{MM}{sep}{name}")
    dialog.s_case.set("kebab-case")
    dialog._save_scheme_as_new()
    saved = controller.library.get_scheme("compact")
    assert saved.pattern == "{YY}{MM}{sep}{name}" and saved.case == "kebab"
    assert dialog.s_example.get().startswith("Example:  2611-my-project")

    dialog.s_pattern.set("{oops}")
    assert dialog.s_example.get().startswith("⚠")

    dialog.close()
    closed.assert_called_once()
    reloaded = SettingsStore(controller.store.file).load()
    assert [s.id for s in reloaded.user_schemes] == ["compact"]


def test_settings_dialog_template_actions(env, tmp_path):
    handles, _, settings_dialog, controller, root, _ = env
    folder = tmp_path / "Tpl"
    folder.mkdir()
    handles.filedialog.askdirectory.return_value = str(folder)
    dialog = settings_dialog.SettingsDialog(root, controller)
    dialog._add_template()
    assert dialog._selected_template().name == "Tpl"
    dialog._set_default_template()
    assert controller.settings.default_template_id == dialog._selected_template().id
    dialog._remove_template()
    assert all(t.name != "Tpl" for t in controller.library.templates)
    assert controller.settings.default_template_id == "motion-video"


def test_template_editor_edits_builtin_as_copy(env):
    handles, main_window, _, controller, root, dest = env
    win = main_window.MainWindow(root, controller)
    editor = handles.template_editor.TemplateEditor(root, controller.library, controller.template, on_saved=win._after_template_saved)
    assert editor.is_copy and editor.name_var.get() == "Motion / Video copy"
    assert editor.folders()[:2] == ["01-Assets", "01-Assets/01-Doc"]

    # rename 04-Footages -> 04-Footage
    tree = editor.tree
    assets = tree.get_children("")[0]
    footages = [c for c in tree.get_children(assets) if tree.item(c, "text") == "04-Footages"][0]
    tree.selection_set(footages)
    handles.simpledialog.askstring.return_value = "04-Footage"
    editor.rename_folder()
    # add a subfolder under 05-Audio, then delete 03-Vector & Fonts, move 02 up
    audio = [c for c in tree.get_children(assets) if tree.item(c, "text") == "05-Audio"][0]
    tree.selection_set(audio)
    handles.simpledialog.askstring.return_value = "Music"
    editor.add_subfolder()
    vector = [c for c in tree.get_children(assets) if tree.item(c, "text") == "03-Vector & Fonts"][0]
    tree.selection_set(vector)
    editor.delete_folder()
    images = [c for c in tree.get_children(assets) if tree.item(c, "text") == "02-Images & PSDs"][0]
    tree.selection_set(images)
    editor.move(-1)
    editor.name_var.set("Motion Lite")
    editor.save()

    saved = controller.library.get_template("motion-lite")
    assert saved.name == "Motion Lite" and not saved.builtin
    assert saved.folders == (
        "01-Assets", "01-Assets/02-Images & PSDs", "01-Assets/01-Doc", "01-Assets/04-Footage",
        "01-Assets/05-Audio", "01-Assets/05-Audio/Music", "02-Project Files", "02-Project Files/_archive",
        "03-Final Output", "03-Final Output/_archive",
    )
    assert controller.template_id == "motion-lite"
    assert win.template_combo["values"][-1] == "Motion Lite (mine)"
    assert controller.library.get_template("motion-video").builtin  # untouched
    assert "Music" in win.tree_text.content


def test_template_editor_rejects_duplicate_sibling_and_bad_names(env):
    handles, _, _, controller, root, _ = env
    editor = handles.template_editor.TemplateEditor(root, controller.library, controller.template)
    tree = editor.tree
    handles.simpledialog.askstring.return_value = "01-Assets"
    editor.add_folder()
    handles.messagebox.showwarning.assert_called()
    assert editor.folders().count("01-Assets") == 1
    handles.simpledialog.askstring.side_effect = ["a/b", None]  # invalid then cancel
    editor.add_folder()
    assert "a-b" in editor.folders() or handles.messagebox.showwarning.called
    handles.simpledialog.askstring.side_effect = None
    editor.close()


def test_template_editor_keeps_files_when_folder_renamed(env):
    handles, _, _, controller, root, _ = env
    web = controller.library.get_template("web-dev")
    editor = handles.template_editor.TemplateEditor(root, controller.library, web)
    files = editor._current_files()
    assert "README.md" in files and files["README.md"].startswith("# {{project_name}}")
    editor.save()
    saved = controller.library.get_template("web-dev-copy")
    assert saved.files["README.md"] == web.files["README.md"]


def test_settings_dialog_duplicate_rename_delete(env):
    handles, _, settings_dialog, controller, root, _ = env
    dialog = settings_dialog.SettingsDialog(root, controller)
    dialog._duplicate_template()
    sel = dialog._selected_template()
    assert sel.name == "Motion / Video copy" and "[mine]" in dialog.template_list.rows[dialog.template_list.selected[0]]
    handles.simpledialog.askstring.return_value = "Client Work"
    dialog._rename_template()
    assert dialog._selected_template().name == "Client Work"
    dialog._remove_template()  # askyesno fake returns True
    assert all(t.name != "Client Work" for t in controller.library.templates)
