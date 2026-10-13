"""Poster POS API helpers for Craft Coffee loyalty."""
from __future__ import annotations

import logging
import re
from typing import Any

import requests

from config import (
    POSTER_CLIENT_GROUP_ID,
    POSTER_CLIENT_GROUP_NAME,
    POSTER_MONEY_MULT,
    POSTER_TOKEN,
)
from services.poster_cache import get_cached

log = logging.getLogger(__name__)

API = "https://joinposter.com/api"
POSTER_CDN = "https://joinposter.com"
TIMEOUT = 25

# Closed receipt status may be 2 or 4 depending on Poster account
CLOSED_TRANSACTION_STATUSES = frozenset({"2", "4"})


def is_transaction_closed(tx: dict | None) -> bool:
    if not tx:
        return False
    return str(tx.get("status") or "") in CLOSED_TRANSACTION_STATUSES


class PosterError(Exception):
    def __init__(self, payload: Any):
        self.payload = payload
        super().__init__(str(payload))


def _token() -> str:
    if not POSTER_TOKEN:
        raise PosterError("POSTER_TOKEN не задано")
    return POSTER_TOKEN


def call(method: str, data: dict | None = None, params: dict | None = None) -> Any:
    url = f"{API}/{method}"
    query = {"token": _token(), **(params or {})}
    if data is None:
        resp = requests.get(url, params=query, timeout=TIMEOUT)
    else:
        resp = requests.post(url, params=query, data=data, timeout=TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise PosterError(body)
    return body.get("response")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    if len(digits) == 11 and digits.startswith("80"):
        digits = "3" + digits
    if not (len(digits) == 12 and digits.startswith("380")):
        raise ValueError(f"Некоректний український номер: {raw}")
    return "+" + digits


def phone_digits(raw: str) -> str:
    return re.sub(r"\D", "", normalize_phone(raw))


def to_minor(amount_uah: float) -> int:
    """Receipts/menu — minor units."""
    return int(round(float(amount_uah) * POSTER_MONEY_MULT))


def from_minor(amount) -> float:
    """Receipts, menu and bonus balance from API — minor units to UAH."""
    try:
        return float(amount or 0) / POSTER_MONEY_MULT
    except (TypeError, ValueError):
        return 0.0


def to_bonus_write(amount_uah: float) -> int:
    """bonus / changeClientBonus.count — amount in UAH (no ×100)."""
    return int(round(float(amount_uah)))


def from_bonus_write(amount) -> float:
    return float(amount or 0)


def ean13_from_seq(seq: int) -> str:
    """Unique internal EAN-13 (prefix 2)."""
    base = "2" + f"{seq % 10**11:011d}"
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base))
    return base + str((10 - total % 10) % 10)


_active_client_group_id: int | None = None


def get_groups() -> list[dict]:
    return call("clients.getGroups") or []


def _group_id_from_row(g: dict) -> int | None:
    raw = g.get("client_groups_id") or g.get("id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _group_name_from_row(g: dict) -> str:
    return str(g.get("client_groups_name") or g.get("name") or "").strip()


def resolve_client_group_id_by_name(name: str) -> int | None:
    want = (name or "").strip().casefold()
    if not want:
        return None
    for g in get_groups():
        if _group_name_from_row(g).casefold() == want:
            return _group_id_from_row(g)
    return None


def init_client_group() -> int:
    """Resolve loyalty client group («Бонуси») on bot startup."""
    global _active_client_group_id
    resolved = resolve_client_group_id_by_name(POSTER_CLIENT_GROUP_NAME)
    if resolved is not None:
        _active_client_group_id = resolved
        log.info(
            "Poster client group «%s» → id=%s",
            POSTER_CLIENT_GROUP_NAME,
            _active_client_group_id,
        )
    else:
        _active_client_group_id = POSTER_CLIENT_GROUP_ID
        log.warning(
            "Групу «%s» не знайдено в Poster — використовуємо POSTER_CLIENT_GROUP_ID=%s",
            POSTER_CLIENT_GROUP_NAME,
            _active_client_group_id,
        )
    return _active_client_group_id


def client_group_id() -> int:
    if _active_client_group_id is not None:
        return _active_client_group_id
    return POSTER_CLIENT_GROUP_ID


def assign_client_group(client_id: int | str) -> None:
    update_client(client_id, client_groups_id_client=client_group_id())


def migrate_registered_bot_clients_to_group() -> tuple[int, int]:
    """Move all bot clients into the target group. Returns (ok, failed)."""
    from database_functions.client_db import registered_poster_client_ids

    gid = client_group_id()
    ok = 0
    failed = 0
    for cid in sorted(registered_poster_client_ids()):
        try:
            update_client(cid, client_groups_id_client=gid)
            ok += 1
        except PosterError as exc:
            failed += 1
            log.warning("client_groups migrate client_id=%s: %s", cid, exc)
    log.info(
        "Poster group migrate «%s» (id=%s): ok=%s failed=%s",
        POSTER_CLIENT_GROUP_NAME,
        gid,
        ok,
        failed,
    )
    return ok, failed


def media_url(path: str | None) -> str | None:
    if not path or not str(path).strip():
        return None
    p = str(path).strip()
    if p.startswith("http://") or p.startswith("https://"):
        return p
    if not p.startswith("/"):
        p = "/" + p
    return f"{POSTER_CDN}{p}"


def get_spots() -> list[dict]:
    return get_cached("spots", lambda: call("access.getSpots") or [])


def get_spot_ids() -> list[int]:
    """All Poster spot_id values (one client can buy at any of them)."""
    ids: list[int] = []
    for s in get_spots():
        raw = s.get("spot_id") or s.get("id")
        try:
            sid = int(raw)
        except (TypeError, ValueError):
            continue
        if sid > 0:
            ids.append(sid)
    return sorted(set(ids))


def get_categories() -> list[dict]:
    return get_cached("categories", lambda: call("menu.getCategories") or [])


def _fetch_products_raw() -> list[dict]:
    return call("menu.getProducts") or []


def get_products(spot_id: int | None = None) -> list[dict]:
    items = get_cached("products", _fetch_products_raw)
    if spot_id is None:
        return items
    visible = []
    for p in items:
        spots = p.get("spots") or []
        if not spots:
            visible.append(p)
            continue
        if any(
            int(s.get("spot_id", 0)) == int(spot_id) and str(s.get("visible", "1")) == "1"
            for s in spots
        ):
            visible.append(p)
    return visible


def get_client(client_id: int | str) -> dict | None:
    try:
        result = call("clients.getClient", params={"client_id": client_id})
    except PosterError as exc:
        # Unknown / deleted client on this account
        payload = exc.payload if isinstance(exc.payload, dict) else {}
        err = payload.get("error")
        if err in (32, 34) or "undefined" in str(payload).lower() or "empty" in str(payload).lower():
            return None
        raise
    if isinstance(result, list):
        return result[0] if result else None
    if isinstance(result, dict):
        return result
    return None


def get_client_bonus_uah(client_id: int | str) -> float:
    """Live client bonus balance from Poster (UAH)."""
    client = get_client(client_id) or {}
    return from_minor(client.get("bonus"))


def get_clients(*, phone: str | None = None) -> list[dict]:
    params: dict[str, Any] = {}
    if phone:
        # Poster accepts local / intl forms; pass digits and +digits.
        digits = re.sub(r"\D", "", phone)
        params["phone"] = digits or phone
    return call("clients.getClients", params=params or None) or []


def find_client_by_phone(phone: str) -> dict | None:
    want = phone_digits(phone)
    tail = want[-9:]
    # Prefer server-side phone filter (full client base can be huge / incomplete without it).
    candidates = get_clients(phone=want) or get_clients(phone=tail) or []
    if not candidates:
        candidates = get_clients()
    for c in candidates:
        raw = c.get("phone_number") or c.get("phone") or ""
        digits = re.sub(r"\D", "", str(raw))
        if digits == want or digits.endswith(tail):
            return c
    return None


def find_clients_by_phone_suffix(suffix: str) -> list[dict]:
    """Find clients by last phone digits (4–12), Nova Poshta style."""
    digits = re.sub(r"\D", "", suffix or "")
    if len(digits) < 4:
        return []
    matches: list[dict] = []
    candidates = get_clients(phone=digits) or get_clients()
    for c in candidates:
        raw = c.get("phone_number") or c.get("phone") or ""
        phone = re.sub(r"\D", "", str(raw))
        if phone.endswith(digits):
            matches.append(c)
    return matches


def create_client(
    *,
    name: str,
    phone: str,
    card_number: str,
    group_id: int | None = None,
    birthday: str | None = None,
    bonus_uah: float = 0,
    sex: int | None = None,
) -> int:
    payload: dict[str, Any] = {
        "client_name": name,
        "client_groups_id_client": group_id or client_group_id(),
        "card_number": card_number,
        "phone": normalize_phone(phone),
    }
    if birthday:
        payload["birthday"] = birthday
    if sex is not None:
        payload["client_sex"] = sex
    if bonus_uah:
        payload["bonus"] = to_bonus_write(bonus_uah)
    result = call("clients.createClient", data=payload)
    return int(result)


def update_client(client_id: int | str, **fields) -> Any:
    payload = {"client_id": client_id, **fields}
    return call("clients.updateClient", data=payload)


def set_bonus(client_id: int | str, amount_uah: float) -> Any:
    return update_client(client_id, bonus=to_bonus_write(amount_uah))


def change_client_bonus(client_id: int | str, delta_uah: float) -> Any:
    """Credit (positive) or debit (negative) bonuses. Returns new balance."""
    return call(
        "clients.changeClientBonus",
        data={
            "client_id": client_id,
            "count": to_bonus_write(delta_uah),
            "block_webhook": "1",
        },
    )


def close_transaction(
    *,
    spot_id: int,
    transaction_id: int | str,
    payed_cash: int | None = None,
    payed_card: int | None = None,
    spot_tablet_id: int = 1,
    print_fiscal: int = 0,
) -> dict:
    """Close a receipt (payed_* amounts in Poster minor units)."""
    payload: dict[str, Any] = {
        "spot_id": int(spot_id),
        "spot_tablet_id": int(spot_tablet_id),
        "transaction_id": int(transaction_id),
        "print_fiscal": int(print_fiscal),
    }
    if payed_cash is not None:
        payload["payed_cash"] = int(payed_cash)
    if payed_card is not None:
        payload["payed_card"] = int(payed_card)
    return call("transactions.closeTransaction", data=payload)


def get_transaction(transaction_id: int | str) -> dict | None:
    result = call(
        "dash.getTransaction",
        params={
            "transaction_id": transaction_id,
            "include_products": "true",
        },
    )
    if isinstance(result, list) and result:
        return result[0]
    if isinstance(result, dict):
        return result
    return None


def _fetch_transactions_range(
    *,
    date_from: str,
    date_to: str,
    spot_id: int | None = None,
) -> list[dict]:
    params: dict[str, Any] = {
        "dateFrom": date_from,
        "dateTo": date_to,
        "include_products": "false",
    }
    if spot_id is not None:
        params["spot_id"] = int(spot_id)
    return call("dash.getTransactions", params=params) or []


def get_closed_transactions(days: int = 2, spot_id: int | None = None) -> list[dict]:
    """Closed receipts for the last `days` days.

    When spot_id is omitted, loads every Poster spot and merges by transaction_id.
    One loyalty client can pay at any venue — do not filter by a single spot.
    """
    from datetime import datetime, timedelta

    date_to = datetime.now()
    date_from = date_to - timedelta(days=max(1, int(days)))
    df = date_from.strftime("%Y%m%d")
    dt = date_to.strftime("%Y%m%d")

    if spot_id is not None:
        items = _fetch_transactions_range(date_from=df, date_to=dt, spot_id=int(spot_id))
        return [t for t in items if is_transaction_closed(t)]

    by_id: dict[str, dict] = {}
    spot_ids = get_spot_ids()
    if not spot_ids:
        # Fallback: account-wide call (covers accounts where spots list is empty)
        for t in _fetch_transactions_range(date_from=df, date_to=dt):
            tid = transaction_id_from_row(t)
            if tid and is_transaction_closed(t):
                by_id[tid] = t
        return list(by_id.values())

    for sid in spot_ids:
        try:
            rows = _fetch_transactions_range(date_from=df, date_to=dt, spot_id=sid)
        except Exception:
            log.exception("get_closed_transactions spot_id=%s failed", sid)
            continue
        for t in rows:
            if not is_transaction_closed(t):
                continue
            tid = transaction_id_from_row(t)
            if tid:
                by_id[tid] = t
    return list(by_id.values())


def transaction_id_from_row(tx: dict) -> str | None:
    raw = tx.get("transaction_id") or tx.get("id") or tx.get("order_id")
    if raw is None or raw == "":
        return None
    return str(raw)


def transaction_spot_id(tx: dict | None) -> int | None:
    if not tx:
        return None
    raw = tx.get("spot_id")
    try:
        sid = int(raw)
    except (TypeError, ValueError):
        return None
    return sid if sid > 0 else None


def get_transactions_for_client(client_id: int | str, days: int = 90) -> list[dict]:
    """Closed receipts for a client over the last `days` days (any spot)."""
    cid = str(client_id)
    return [t for t in get_closed_transactions(days=days) if str(t.get("client_id") or "") == cid]


def product_by_id(product_id: int | str) -> dict | None:
    pid = str(product_id)
    for p in get_products():
        if str(p.get("product_id")) == pid:
            return p
    return None


def category_by_id(category_id: int | str) -> dict | None:
    cid = str(category_id)
    for c in get_categories():
        if str(c.get("category_id")) == cid:
            return c
    return None


def product_price_uah(product: dict, spot_id: int | None = None) -> float | None:
    spots = product.get("spots") or []
    for s in spots:
        if spot_id is None or int(s.get("spot_id", 0)) == int(spot_id):
            price = s.get("price")
            if price is not None:
                return from_minor(price)
    return None
