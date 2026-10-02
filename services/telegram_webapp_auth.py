"""Перевірка Telegram WebApp initData (як у aiogram + fallback для signature)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from aiogram.utils.web_app import safe_parse_webapp_init_data

log = logging.getLogger(__name__)


def _validate_hash(init_data: str, bot_token: str, exclude_signature: bool) -> dict | None:
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        return None
    received = parsed.pop("hash", None)
    if not received:
        return None
    if exclude_signature:
        parsed.pop("signature", None)
    check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        return None
    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    try:
        auth_date = int(parsed.get("auth_date") or 0)
    except (TypeError, ValueError):
        auth_date = 0
    return {"user": user, "auth_date": auth_date}


def parse_telegram_user(init_data: str, bot_token: str, max_age_sec: int = 0) -> dict | None:
    """
    Повертає dict користувача Telegram (мінімум id) або None.
    max_age_sec=0 — не перевіряти застарілість auth_date.
    """
    if not init_data or not bot_token:
        return None

    init_data = init_data.strip()

    try:
        data = safe_parse_webapp_init_data(bot_token, init_data)
        if data.user:
            if max_age_sec > 0 and data.auth_date:
                age = time.time() - data.auth_date.timestamp()
                if age > max_age_sec:
                    log.info("webapp initData expired (age=%.0fs)", age)
                    return None
            return {
                "id": data.user.id,
                "first_name": data.user.first_name,
                "last_name": data.user.last_name,
                "username": data.user.username,
            }
    except ValueError:
        pass

    for exclude_sig in (True, False):
        raw = _validate_hash(init_data, bot_token, exclude_signature=exclude_sig)
        if not raw:
            continue
        if max_age_sec > 0 and raw["auth_date"] > 0:
            if time.time() - raw["auth_date"] > max_age_sec:
                log.info("webapp initData expired (fallback)")
                return None
        return raw["user"]

    return None
