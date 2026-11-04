"""Validation of Telegram Mini App `initData` (HMAC-SHA256).

Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
Without this check anyone could call the API pretending to be another user.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InitDataError(ValueError):
    pass


def validate_init_data(init_data: str, bot_token: str, *, max_age: int = 86400, now: float | None = None) -> dict:
    """Return the Telegram user dict from a valid initData string, else raise InitDataError."""
    if not init_data:
        raise InitDataError("empty init data")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("hash is missing")

    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("signature mismatch")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise InitDataError("bad auth_date") from exc
    current = time.time() if now is None else now
    if auth_date <= 0 or current - auth_date > max_age:
        raise InitDataError("init data expired")

    try:
        user = json.loads(pairs.get("user", ""))
        int(user["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InitDataError("user is missing") from exc
    return user


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Build a valid initData string. Used only by tests and local tooling."""
    from urllib.parse import urlencode

    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})
