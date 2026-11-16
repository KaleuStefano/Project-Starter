import subprocess
from pathlib import Path

import pytest

from oneclick.system import shortcut


def test_linux_desktop_file(tmp_path, monkeypatch):
    monkeypatch.setattr(shortcut.sys, "platform", "linux")
    monkeypatch.setattr(shortcut, "desktop_dir", lambda: tmp_path)
    path = shortcut.create_desktop_shortcut()
    text = path.read_text()
    assert path.name == "project-starter.desktop" and "run.py" in text and "Terminal=false" in text
    assert shortcut.shortcut_exists()
    shortcut.remove_desktop_shortcut()
    assert not shortcut.shortcut_exists()


def test_windows_builds_powershell_shortcut(tmp_path, monkeypatch):
    monkeypatch.setattr(shortcut.sys, "platform", "win32")
    monkeypatch.setattr(shortcut, "desktop_dir", lambda: tmp_path)
    monkeypatch.setattr(shortcut, "launch_command", lambda: [r"C:\Py\pythonw.exe", r"C:\Dev\project-starter\run.py"])
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["script"] = cmd[-1]
        (tmp_path / "Project Starter.lnk").write_bytes(b"lnk")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(shortcut.subprocess, "run", fake_run)
    path = shortcut.create_desktop_shortcut()
    assert path.name == "Project Starter.lnk"
    assert "TargetPath = 'C:\\Py\\pythonw.exe'" in calls["script"]
    assert "run.py" in calls["script"] and "IconLocation" in calls["script"]


def test_windows_failure_is_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(shortcut.sys, "platform", "win32")
    monkeypatch.setattr(shortcut, "desktop_dir", lambda: tmp_path)
    monkeypatch.setattr(shortcut.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, "", "access denied"))
    with pytest.raises(RuntimeError, match="access denied"):
        shortcut.create_desktop_shortcut()


def test_mac_command_file_from_source(tmp_path, monkeypatch):
    monkeypatch.setattr(shortcut.sys, "platform", "darwin")
    monkeypatch.setattr(shortcut, "desktop_dir", lambda: tmp_path)
    path = shortcut.create_desktop_shortcut()
    assert path.suffix == ".command" and path.stat().st_mode & 0o111
    assert "run.py" in path.read_text()
