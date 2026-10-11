"""Telegram Mini App initData validation and at-rest encryption of Moodle secrets."""

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class InitDataError(ValueError):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age: int = 24 * 3600) -> dict:
    """Validate `Telegram.WebApp.initData` and return the parsed fields (with `user` decoded).

    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        raise InitDataError("empty initData")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("hash missing")
    check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        raise InitDataError("bad hash")
    auth_date = int(pairs.get("auth_date", "0"))
    if max_age and time.time() - auth_date > max_age:
        raise InitDataError("initData expired")
    if "user" in pairs:
        pairs["user"] = json.loads(pairs["user"])
    return pairs


def _fernet() -> Fernet:
    key = hashlib.sha256(("moodle-secrets:" + get_settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None
