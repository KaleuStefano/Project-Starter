import datetime as dt

import pytest

from oneclick.core.errors import InvalidNameError, InvalidPatternError
from oneclick.core.naming import (
    BUILTIN_SCHEMES,
    NamingScheme,
    apply_case,
    build_folder_name,
    next_number,
    parse_pattern,
)

NOW = dt.datetime(2026, 11, 14, 9, 30)
DEFAULT = BUILTIN_SCHEMES[0]


def test_default_scheme_matches_v1_format():
    built = build_folder_name(DEFAULT, "My Project", [], NOW)
    assert built.folder_name == "26-01-My Project"
    assert built.number == 1


def test_counter_is_highest_plus_one_not_count():
    existing = ["26-03-A", "26-07-B"]
    assert build_folder_name(DEFAULT, "C", existing, NOW).folder_name == "26-08-C"


def test_counter_ignores_non_matching_folders():
    existing = ["01-Assets", "02-Project Files", "03-Final Output", "random", "26-04-Real"]
    assert next_number(DEFAULT, existing, NOW) == 5


def test_counter_handles_names_containing_dashes_and_digits():
    # the real folder this project lives in
    assert next_number(DEFAULT, ["26-12-1-Click_Database-Update"], NOW) == 13


def test_counter_continue_scope_spans_years():
    existing = ["25-14-Old", "26-02-New"]
    assert next_number(DEFAULT, existing, NOW) == 15


def test_counter_per_year_scope_restarts():
    scheme = DEFAULT.with_changes(counter_scope="per_year")
    assert next_number(scheme, ["25-14-Old", "24-30-Older"], NOW) == 1
    assert next_number(scheme, ["25-14-Old", "26-02-New"], NOW) == 3


def test_per_year_with_four_digit_year():
    scheme = NamingScheme("x", "x", pattern="{YYYY}{sep}{NN}{sep}{name}", counter_scope="per_year")
    assert next_number(scheme, ["2025-09-A", "2026-04-B"], NOW) == 5


def test_per_year_without_year_token_behaves_like_continue():
    scheme = NamingScheme("x", "x", pattern="{NN}{sep}{name}", counter_scope="per_year")
    assert next_number(scheme, ["03-A", "09-B"], NOW) == 10


def test_pattern_without_counter_returns_no_number():
    scheme = NamingScheme("x", "x", pattern="{YYYY}{MM}{DD}{sep}{name}")
    built = build_folder_name(scheme, "Shoot", ["whatever"], NOW)
    assert built.number is None
    assert built.folder_name == "20261114-Shoot"


def test_padding_and_separator():
    scheme = NamingScheme("x", "x", pad=3, sep="_")
    assert build_folder_name(scheme, "Foo", [], NOW).folder_name == "26_001_Foo"
    # existing folders with the same separator are recognised
    assert next_number(scheme, ["26_009_A"], NOW) == 10


def test_number_wider_than_pad_still_works():
    assert build_folder_name(DEFAULT, "Z", ["26-99-A"], NOW).folder_name == "26-100-Z"


@pytest.mark.parametrize(
    "style,expected",
    [
        ("keep", "my Great_project"),
        ("title", "My Great_project"),
        ("kebab", "my-great-project"),
        ("snake", "my_great_project"),
    ],
)
def test_case_styles(style, expected):
    assert apply_case("my Great_project", style) == expected


def test_title_case_keeps_digits_and_inner_caps():
    assert apply_case("1-click tool", "title") == "1-click Tool"


@pytest.mark.parametrize(
    "pattern",
    [
        "",
        "{name",
        "{foo}{name}",
        "{YY}-{NN}",  # missing {name}
        "{name}{name}",
        "{YY}{YY}{name}",
        "{YY}{YYYY}{name}",
        "{NN}{NN}{name}",
        "a/b{name}",
        "{name}:",
    ],
)
def test_invalid_patterns_rejected(pattern):
    with pytest.raises(InvalidPatternError):
        parse_pattern(pattern)


def test_scheme_validation_of_options():
    with pytest.raises(InvalidPatternError):
        NamingScheme("x", "x", pad=0).validate()
    with pytest.raises(InvalidPatternError):
        NamingScheme("x", "x", sep="/").validate()
    with pytest.raises(InvalidPatternError):
        NamingScheme("x", "x", case="shouty").validate()


def test_empty_and_unusable_names():
    with pytest.raises(InvalidNameError):
        build_folder_name(DEFAULT, "   ", [], NOW)
    with pytest.raises(InvalidNameError):
        build_folder_name(DEFAULT, " . . . ", [], NOW)  # nothing left after sanitising
    with pytest.raises(InvalidNameError):
        build_folder_name(DEFAULT.with_changes(case="kebab"), "- _ -", [], NOW)  # nothing left after case style


def test_illegal_characters_are_replaced_and_flagged():
    built = build_folder_name(DEFAULT, 'Client: "Acme"/Launch', [], NOW)
    assert built.folder_name == "26-01-Client- -Acme--Launch"
    assert built.name_adjusted


def test_name_adjusted_false_for_plain_names():
    assert not build_folder_name(DEFAULT, "Plain  Name ", [], NOW).name_adjusted


def test_reserved_windows_name_rejected_when_whole_folder_name():
    scheme = NamingScheme("x", "x", pattern="{name}")
    with pytest.raises(InvalidNameError):
        build_folder_name(scheme, "con", [], NOW)


def test_scheme_dict_roundtrip_and_tolerance():
    scheme = NamingScheme("mine", "Mine", pattern="{YYYY}{sep}{name}", sep="_", pad=3, case="snake")
    assert NamingScheme.from_dict(scheme.to_dict()) == scheme
    broken = NamingScheme.from_dict({"id": "a", "pad": "wide"})
    assert broken.pad == 2 and broken.label == "a"
