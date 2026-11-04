import json

import pytest

from bot.webapp_auth import InitDataError, sign_init_data, validate_init_data

TOKEN = "123456:TEST-TOKEN"
NOW = 1_900_000_000.0


def make(user=None, auth_date=NOW - 60, token=TOKEN, **extra):
    fields = {
        "auth_date": str(int(auth_date)),
        "query_id": "AAH123",
        "user": json.dumps(user or {"id": 42, "first_name": "Anna"}),
        **extra,
    }
    return sign_init_data(fields, token)


def test_valid_init_data_returns_the_user():
    user = validate_init_data(make(), TOKEN, now=NOW)
    assert user["id"] == 42 and user["first_name"] == "Anna"


def test_wrong_token_is_rejected():
    with pytest.raises(InitDataError):
        validate_init_data(make(token="999:OTHER"), TOKEN, now=NOW)


def test_tampered_payload_is_rejected():
    data = make().replace("42", "43")
    with pytest.raises(InitDataError):
        validate_init_data(data, TOKEN, now=NOW)


def test_expired_data_is_rejected():
    with pytest.raises(InitDataError, match="expired"):
        validate_init_data(make(auth_date=NOW - 90000), TOKEN, now=NOW)


@pytest.mark.parametrize("bad", ["", "user=%7B%7D", "hash=abc", "auth_date=1&hash=zzz"])
def test_garbage_is_rejected(bad):
    with pytest.raises(InitDataError):
        validate_init_data(bad, TOKEN, now=NOW)
