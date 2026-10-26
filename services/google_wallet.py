"""Google Wallet loyalty cards (REST API + Save to Wallet JWT)."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from config import (
    GOOGLE_WALLET_CLASS_SUFFIX,
    GOOGLE_WALLET_ISSUER_ID,
    GOOGLE_WALLET_KEY_FILE,
    WALLET_BG_COLOR,
    WALLET_LOGO_URL,
    WEBAPP_URL,
)

log = logging.getLogger(__name__)

BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]
BARCODE_TYPE = "CODE_128"
ISSUER_NAME = "Крафт Кава"
PROGRAM_NAME = "Бонусна картка Крафт Кава"


class GoogleWalletError(Exception):
    pass


def _class_id() -> str:
    return f"{GOOGLE_WALLET_ISSUER_ID}.{GOOGLE_WALLET_CLASS_SUFFIX}"


def _object_id(card_number: str) -> str:
    return f"{GOOGLE_WALLET_ISSUER_ID}.card_{card_number}"


def is_configured() -> bool:
    return bool(
        GOOGLE_WALLET_ISSUER_ID
        and GOOGLE_WALLET_CLASS_SUFFIX
        and GOOGLE_WALLET_KEY_FILE
        and Path(GOOGLE_WALLET_KEY_FILE).is_file()
    )


def status() -> dict[str, Any]:
    return {
        "configured": is_configured(),
        "issuer_id": bool(GOOGLE_WALLET_ISSUER_ID),
        "class_suffix": bool(GOOGLE_WALLET_CLASS_SUFFIX),
        "credentials": bool(GOOGLE_WALLET_KEY_FILE and Path(GOOGLE_WALLET_KEY_FILE).is_file()),
        "class_id": _class_id() if is_configured() else None,
    }


def _get_session():
    if not is_configured():
        raise GoogleWalletError("Google Wallet не налаштовано на сервері (немає ключа або ISSUER_ID).")
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_WALLET_KEY_FILE, scopes=SCOPES
    )
    return AuthorizedSession(creds)


def _api_error(resp, context: str) -> GoogleWalletError:
    log.warning("google wallet %s: %s %s", context, resp.status_code, resp.text[:500])
    if resp.status_code == 403:
        return GoogleWalletError(
            "Немає доступу до Google Wallet API. Перевірте сервісний акаунт у консолі Wallet."
        )
    try:
        msg = resp.json().get("error", {}).get("message") or resp.text
    except Exception:
        msg = resp.text or context
    return GoogleWalletError(msg or context)


def _build_object_body(object_id: str, card_number: str, name: str, points: int) -> dict:
    return {
        "id": object_id,
        "classId": _class_id(),
        "state": "ACTIVE",
        "accountId": card_number,
        "accountName": name,
        "barcode": {
            "type": BARCODE_TYPE,
            "value": card_number,
            "alternateText": card_number,
        },
        "loyaltyPoints": {
            "label": "Крафтики",
            "balance": {"int": max(0, int(points))},
        },
    }


def _ensure_class(session) -> None:
    class_id = _class_id()
    r = session.get(f"{BASE}/loyaltyClass/{class_id}")
    if r.status_code == 200:
        return
    if r.status_code != 404:
        raise _api_error(r, "loyaltyClass get")
    logo = (WALLET_LOGO_URL or "").strip()
    if not logo and WEBAPP_URL:
        logo = f"{WEBAPP_URL.rstrip('/')}/logo.png"
    if not logo:
        raise GoogleWalletError("Клас Google Wallet не створено. Задайте WALLET_LOGO_URL у .env.")
    body = {
        "id": class_id,
        "issuerName": ISSUER_NAME,
        "programName": PROGRAM_NAME,
        "programLogo": {
            "sourceUri": {"uri": logo},
            "contentDescription": {"defaultValue": {"language": "uk", "value": "Логотип Крафт Кава"}},
        },
        "hexBackgroundColor": WALLET_BG_COLOR,
        "reviewStatus": "UNDER_REVIEW",
    }
    r = session.post(f"{BASE}/loyaltyClass", json=body)
    if r.status_code != 200:
        raise _api_error(r, "loyaltyClass create")


def _sync_object(session, card_number: str, name: str, points: int) -> str:
    object_id = _object_id(card_number)
    body = _build_object_body(object_id, card_number, name, points)
    r = session.get(f"{BASE}/loyaltyObject/{object_id}")
    if r.status_code == 200:
        patch = {
            "accountName": name,
            "loyaltyPoints": body["loyaltyPoints"],
            "barcode": body["barcode"],
        }
        r = session.patch(f"{BASE}/loyaltyObject/{object_id}", json=patch)
        if r.status_code != 200:
            raise _api_error(r, "loyaltyObject patch")
    elif r.status_code == 404:
        r = session.post(f"{BASE}/loyaltyObject", json=body)
        if r.status_code != 200:
            raise _api_error(r, "loyaltyObject create")
    else:
        raise _api_error(r, "loyaltyObject get")
    return object_id


def _save_url(object_id: str) -> str:
    from google.auth import crypt, jwt

    signer = crypt.RSASigner.from_service_account_file(GOOGLE_WALLET_KEY_FILE)
    with open(GOOGLE_WALLET_KEY_FILE, encoding="utf-8") as f:
        sa_email = json.load(f)["client_email"]
    claims = {
        "iss": sa_email,
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "origins": [],
        "payload": {"loyaltyObjects": [{"id": object_id}]},
    }
    token = jwt.encode(signer, claims).decode("utf-8")
    return f"https://pay.google.com/gp/v/save/{token}"


def create_save_link(card_number: str, name: str, bonus_uah: float) -> str:
    """Create or update loyalty object; return Add to Google Wallet URL."""
    session = _get_session()
    _ensure_class(session)
    points = int(round(float(bonus_uah or 0)))
    object_id = _sync_object(session, card_number, name, points)
    return _save_url(object_id)
