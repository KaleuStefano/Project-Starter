import pytest

from oneclick.core.errors import InvalidNameError
from oneclick.core.models import TemplateEntry
from oneclick.core.sanitize import sanitize_name, validate_component
from oneclick.core.tree import render_tree


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Plain", "Plain"),
        ("  spaced   out  ", "spaced out"),
        ("a/b\\c", "a-b-c"),
        ('x:y*z?"<>|', "x-y-z-----"),
        ("line\nbreak", "line break"),
        ("trailing dot.", "trailing dot"),
        ("...hidden", "hidden"),
        ("tab\there", "tab here"),
        ("ctrl\x00char", "ctrlchar"),
        ("café", "café"),
    ],
)
def test_sanitize(raw, expected):
    assert sanitize_name(raw) == expected


@pytest.mark.parametrize("bad", ["", " ", "CON", "nul", "com1", "LPT9.txt", "a" * 300, "bad|name", "trail.", " lead"])
def test_validate_component_rejects(bad):
    with pytest.raises(InvalidNameError):
        validate_component(bad)


@pytest.mark.parametrize("good", ["26-01-Project", "console", "COM10", "Résumé", "a.b"])
def test_validate_component_accepts(good):
    validate_component(good)


def test_render_tree_layout():
    entries = [
        TemplateEntry("01-Assets", True),
        TemplateEntry("01-Assets/01-Doc", True),
        TemplateEntry("01-Assets/02-Images", True),
        TemplateEntry("README.md", False, 10),
        TemplateEntry("02-Out", True),
    ]
    assert render_tree("26-01-X", entries) == [
        "26-01-X",
        "├─ 01-Assets",
        "│  ├─ 01-Doc",
        "│  └─ 02-Images",
        "├─ 02-Out",
        "└─ README.md",
    ]


def test_render_tree_truncates():
    entries = [TemplateEntry(f"d{i:03d}", True) for i in range(300)]
    lines = render_tree("root", entries, max_lines=50)
    assert len(lines) == 51
    assert lines[-1].startswith("… and")
