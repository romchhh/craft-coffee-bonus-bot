"""Push balance updates to Apple Wallet (APNs) and Google Wallet (PATCH)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from database_functions.client_db import get_user
from database_functions import wallet_passes_db as wdb
from services import apple_wallet, google_wallet, poster

log = logging.getLogger(__name__)

# Avoid APNs storms (many cards on one phone / bulk burn jobs)
_APNS_MIN_INTERVAL_SEC = 45.0
_last_apns_at: dict[str, float] = {}
_apns_lock = threading.Lock()
_httpx_client = None
_httpx_lock = threading.Lock()


def _current_bonus(user: dict) -> float:
    cid = user.get("poster_client_id")
    if not cid:
        return 0.0
    try:
        return float(poster.get_client_bonus_uah(cid) or 0)
    except Exception as exc:
        log.warning("wallet sync: get bonus failed user=%s: %s", user.get("user_id"), exc)
        return 0.0


def sync_google_wallet(user: dict, bonus: float) -> None:
    if not google_wallet.is_configured():
        return
    card = (user.get("card_number") or "").strip()
    if not card:
        return
    name = user.get("display_name") or user.get("user_first_name") or "Гість"
    try:
        google_wallet.update_balance(card, name, bonus)
    except Exception as exc:
        log.warning("google wallet sync user=%s: %s", user.get("user_id"), exc)


def _apns_client():
    global _httpx_client
    if not apple_wallet.is_configured():
        return None
    from config import (
        APPLE_PASS_CERT,
        APPLE_PASS_KEY,
        APPLE_PASS_KEY_PASSWORD,
    )

    try:
        import httpx
    except ImportError:
        log.error("httpx not installed — Apple Wallet push disabled")
        return None

    with _httpx_lock:
        if _httpx_client is None:
            cert = (APPLE_PASS_CERT, APPLE_PASS_KEY, APPLE_PASS_KEY_PASSWORD or None)
            _httpx_client = httpx.Client(http2=True, cert=cert, timeout=15.0)
        return _httpx_client


def _send_apns(push_token: str) -> bool:
    """Silent Wallet update push (empty payload, topic = pass type id)."""
    from config import APPLE_PASS_TYPE_ID

    client = _apns_client()
    if client is None:
        return False

    now = time.monotonic()
    with _apns_lock:
        last = _last_apns_at.get(push_token, 0.0)
        if now - last < _APNS_MIN_INTERVAL_SEC:
            log.debug("APNs debounced token=%s…", push_token[:12])
            return False
        _last_apns_at[push_token] = now

    url = f"https://api.push.apple.com/3/device/{push_token}"
    headers = {
        "apns-topic": APPLE_PASS_TYPE_ID,
        "apns-push-type": "background",
        "apns-priority": "5",
        "content-type": "application/json",
    }
    try:
        resp = client.post(url, content=b"{}", headers=headers)
        if resp.status_code == 200:
            return True
        log.warning(
            "APNs push failed token=%s… status=%s body=%s",
            push_token[:12],
            resp.status_code,
            (resp.text or "")[:200],
        )
        return False
    except Exception as exc:
        log.warning("APNs push error token=%s…: %s", push_token[:12], exc)
        return False


def sync_apple_wallet(user: dict, *, bonus: float | None = None) -> dict[str, Any]:
    """Bump pass update tag and notify registered devices."""
    report: dict[str, Any] = {"pushed": 0, "tokens": 0, "debounced": 0}
    if not apple_wallet.is_configured():
        return report
    serial = wdb.serial_for_user(user)
    wdb.ensure_pass_record(int(user["user_id"]), serial)
    if bonus is not None:
        wdb.set_pass_bonus(serial, float(bonus))
    wdb.bump_pass_updated(serial)
    tokens = wdb.push_tokens_for_serial(serial)
    report["tokens"] = len(tokens)
    for token in tokens:
        if _send_apns(token):
            report["pushed"] += 1
        else:
            report["debounced"] += 1
    return report


def sync_wallets_for_user(user_id: int, *, bonus: float | None = None) -> dict[str, Any]:
    """Refresh Google object + notify Apple Wallet devices for this client."""
    user = get_user(user_id)
    if not user or not user.get("registered"):
        return {"status": "skip", "reason": "no_user"}
    bal = float(bonus) if bonus is not None else _current_bonus(user)
    sync_google_wallet(user, bal)
    apple_report = sync_apple_wallet(user, bonus=bal)
    return {"status": "ok", "bonus": bal, "apple": apple_report}


async def sync_wallets_for_user_async(user_id: int, *, bonus: float | None = None) -> dict[str, Any]:
    import asyncio

    return await asyncio.to_thread(sync_wallets_for_user, user_id, bonus=bonus)
