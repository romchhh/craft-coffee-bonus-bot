"""Push balance updates to Apple Wallet (APNs) and Google Wallet (PATCH)."""
from __future__ import annotations

import logging
from typing import Any

from database_functions.client_db import get_user
from database_functions import wallet_passes_db as wdb
from services import apple_wallet, google_wallet, poster

log = logging.getLogger(__name__)


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


def _send_apns(push_token: str) -> bool:
    """Silent Wallet update push (empty payload, topic = pass type id)."""
    if not apple_wallet.is_configured():
        return False
    from config import (
        APPLE_PASS_CERT,
        APPLE_PASS_KEY,
        APPLE_PASS_KEY_PASSWORD,
        APPLE_PASS_TYPE_ID,
    )

    try:
        import httpx
    except ImportError:
        log.error("httpx not installed — Apple Wallet push disabled")
        return False

    url = f"https://api.push.apple.com/3/device/{push_token}"
    headers = {
        "apns-topic": APPLE_PASS_TYPE_ID,
        "apns-push-type": "background",
        "apns-priority": "5",
        "content-type": "application/json",
    }
    cert = (APPLE_PASS_CERT, APPLE_PASS_KEY, APPLE_PASS_KEY_PASSWORD or None)
    try:
        with httpx.Client(http2=True, cert=cert, timeout=15.0) as client:
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


def sync_apple_wallet(user: dict) -> dict[str, Any]:
    """Bump pass update tag and notify registered devices."""
    report: dict[str, Any] = {"pushed": 0, "tokens": 0}
    if not apple_wallet.is_configured():
        return report
    serial = wdb.serial_for_user(user)
    wdb.ensure_pass_record(int(user["user_id"]), serial)
    wdb.bump_pass_updated(serial)
    tokens = wdb.push_tokens_for_serial(serial)
    report["tokens"] = len(tokens)
    for token in tokens:
        if _send_apns(token):
            report["pushed"] += 1
    return report


def sync_wallets_for_user(user_id: int, *, bonus: float | None = None) -> dict[str, Any]:
    """Refresh Google object + notify Apple Wallet devices for this client."""
    user = get_user(user_id)
    if not user or not user.get("registered"):
        return {"status": "skip", "reason": "no_user"}
    bal = float(bonus) if bonus is not None else _current_bonus(user)
    sync_google_wallet(user, bal)
    apple_report = sync_apple_wallet(user)
    return {"status": "ok", "bonus": bal, "apple": apple_report}


async def sync_wallets_for_user_async(user_id: int, *, bonus: float | None = None) -> dict[str, Any]:
    import asyncio

    return await asyncio.to_thread(sync_wallets_for_user, user_id, bonus=bonus)
