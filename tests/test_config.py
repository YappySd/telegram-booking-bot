import json

import pytest

from bot.config import ConfigError, load_business, load_settings, parse_business
from tests.helpers import BUSINESS_DATA

ENV = {"BOT_TOKEN": "123:ABC", "ADMIN_IDS": "1, 2", "WEBAPP_URL": "https://example.com/"}


def test_settings_defaults_and_parsing():
    s = load_settings(ENV)
    assert s.admin_ids == frozenset({1, 2})
    assert s.webapp_url == "https://example.com"
    assert s.timezone.key == "Europe/Kyiv" and s.port == 8080


def test_settings_repr_never_contains_the_token():
    assert "ABC" not in repr(load_settings(ENV))


@pytest.mark.parametrize(
    "patch",
    [
        {"BOT_TOKEN": ""},
        {"BOT_TOKEN": "no-colon"},
        {"ADMIN_IDS": "abc"},
        {"WEBAPP_URL": "http://insecure.example.com"},
        {"TIMEZONE": "Mars/Base"},
        {"PORT": "x"},
    ],
)
def test_bad_settings_give_readable_errors(patch):
    with pytest.raises(ConfigError):
        load_settings({**ENV, **patch})


def test_webapp_is_optional():
    assert load_settings({"BOT_TOKEN": "1:A"}).webapp_url is None


def test_business_parsing():
    b = parse_business(BUSINESS_DATA)
    assert b.service("cut").minutes == 60 and b.service("nope") is None
    assert b.hours_for(6) == () and len(b.hours_for(1)) == 2
    assert b.reminder_hours == (24, 2)


@pytest.mark.parametrize(
    "patch",
    [
        {"services": []},
        {"step_minutes": 1},
        {"schedule": {"9": [["10:00", "11:00"]]}},
        {"schedule": {"0": [["12:00", "10:00"]]}},
        {"schedule": {"0": [["10:00", "25:99"]]}},
        {"services": [{"id": "a", "title": "A", "minutes": 0, "price": 1}]},
        {"services": [{"id": "a", "title": "A", "minutes": 30, "price": 1}] * 2},
    ],
)
def test_bad_business_is_rejected(patch):
    with pytest.raises(ConfigError):
        parse_business({**BUSINESS_DATA, **patch})


def test_example_business_file_is_valid(tmp_path):
    from pathlib import Path

    business = load_business(Path(__file__).resolve().parent.parent / "business.example.json")
    assert len(business.services) >= 3


def test_missing_and_broken_files(tmp_path):
    with pytest.raises(ConfigError, match="не найден"):
        load_business(tmp_path / "x.json")
    broken = tmp_path / "b.json"
    broken.write_text("{oops", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON"):
        load_business(broken)
    assert json  # silence unused import
