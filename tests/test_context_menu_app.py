import plistlib

import pytest

from oneclick import app
from oneclick.system import context_menu as cm


class FakeRegistry:
    def __init__(self):
        self.keys: dict[str, dict[str, str]] = {}

    def set_default(self, key_path, value):
        self.keys.setdefault(key_path, {})[""] = value

    def set_value(self, key_path, name, value):
        self.keys.setdefault(key_path, {})[name] = value

    def delete_tree(self, key_path):
        for k in [k for k in self.keys if k == key_path or k.startswith(key_path + "\\")]:
            del self.keys[k]

    def exists(self, key_path):
        return any(k == key_path or k.startswith(key_path + "\\") for k in self.keys)


def test_windows_install_and_uninstall():
    reg = FakeRegistry()
    menu = cm.WindowsContextMenu(reg, command=[r"C:\Program Files\OneClick\OneClick.exe"])
    assert not menu.status().installed
    menu.install()
    assert menu.status().installed
    bg = reg.keys[menu.BACKGROUND_KEY + r"\command"][""]
    folder = reg.keys[menu.FOLDER_KEY + r"\command"][""]
    assert bg == folder == r'"C:\Program Files\OneClick\OneClick.exe" --dest "%V"'
    assert reg.keys[menu.BACKGROUND_KEY][""] == "New project here"
    menu.uninstall()
    assert not menu.status().installed and reg.keys == {}


def test_windows_install_is_idempotent():
    reg = FakeRegistry()
    menu = cm.WindowsContextMenu(reg, command=["app.exe"])
    menu.install()
    menu.install()
    assert menu.status().installed


def test_mac_quick_actions_are_valid_plists(tmp_path, monkeypatch):
    monkeypatch.setattr(cm.MacContextMenu, "_refresh_services", staticmethod(lambda: None))
    menu = cm.MacContextMenu(tmp_path / "Services", command=["/Applications/One Click.app/Contents/MacOS/OneClick"])
    assert not menu.status().installed
    menu.install()
    assert menu.status().installed

    folder_dir = tmp_path / "Services" / "New project here.workflow" / "Contents"
    window_dir = tmp_path / "Services" / "New project in this window.workflow" / "Contents"
    info = plistlib.loads((folder_dir / "Info.plist").read_bytes())
    service = info["NSServices"][0]
    assert service["NSMenuItem"]["default"] == "New project here"
    assert service["NSSendFileTypes"] == ["public.folder"]
    wflow = plistlib.loads((folder_dir / "document.wflow").read_bytes())
    script = wflow["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"]
    assert "'/Applications/One Click.app/Contents/MacOS/OneClick' --dest" in script
    assert wflow["workflowMetaData"]["workflowTypeIdentifier"] == "com.apple.Automator.servicesMenu"

    window_info = plistlib.loads((window_dir / "Info.plist").read_bytes())
    assert "NSSendFileTypes" not in window_info["NSServices"][0]
    window_wflow = plistlib.loads((window_dir / "document.wflow").read_bytes())
    assert "osascript" in window_wflow["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"]

    menu.uninstall()
    assert not menu.status().installed and not (tmp_path / "Services" / "New project here.workflow").exists()


def test_launch_command_in_dev_mode_points_at_run_py():
    command = cm.launch_command()
    assert command[-1].endswith("run.py")


def test_unsupported_platform_message():
    status = cm.UnsupportedContextMenu().status()
    assert not status.supported
    with pytest.raises(NotImplementedError):
        cm.UnsupportedContextMenu().install()


# ---- command line ----------------------------------------------------------


def test_clean_dest_handles_quotes_and_missing(tmp_path):
    assert app.clean_dest(None) is None
    assert app.clean_dest("") is None
    assert app.clean_dest(str(tmp_path / "nope")) is None
    assert app.clean_dest(f'"{tmp_path}"') == str(tmp_path)
    assert app.clean_dest(f'{tmp_path}"') == str(tmp_path)  # what Windows passes for "%V" with a trailing slash


def test_parser_options():
    args = app.build_parser().parse_args(["--dest", "D:/x", "--name", "Foo"])
    assert args.dest == "D:/x" and args.name == "Foo" and not args.install_context_menu


def test_main_reports_failure_when_menu_unsupported(monkeypatch, tmp_path):
    monkeypatch.setenv("ONECLICK_HOME", str(tmp_path))
    monkeypatch.setattr(cm, "get_context_menu", cm.UnsupportedContextMenu)
    assert app.main(["--install-context-menu"]) == 1
