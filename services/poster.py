"""Poster POS API helpers for Craft Coffee loyalty."""
from __future__ import annotations

import logging
import re
from typing import Any

import requests

from config import POSTER_BONUS_MULT, POSTER_CLIENT_GROUP_ID, POSTER_TOKEN
from services.poster_cache import get_cached

log = logging.getLogger(__name__)

API = "https://joinposter.com/api"
POSTER_CDN = "https://joinposter.com"
TIMEOUT = 25

# У різних акаунтах Poster закритий чек може бути status 2 або 4
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
    return int(round(float(amount_uah) * POSTER_BONUS_MULT))


def from_minor(amount) -> float:
    try:
        return float(amount or 0) / POSTER_BONUS_MULT
    except (TypeError, ValueError):
        return 0.0


def ean13_from_seq(seq: int) -> str:
    """Унікальний внутрішній EAN-13 (префікс 2)."""
    base = "2" + f"{seq % 10**11:011d}"
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base))
    return base + str((10 - total % 10) % 10)


def get_groups() -> list[dict]:
    return call("clients.getGroups") or []


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
    result = call("clients.getClient", params={"client_id": client_id})
    if isinstance(result, list):
        return result[0] if result else None
    if isinstance(result, dict):
        return result
    return None


def get_client_bonus_uah(client_id: int | str) -> float:
    """Живий баланс бонусів клієнта з Poster (у гривнях)."""
    client = get_client(client_id) or {}
    return from_minor(client.get("bonus"))


def get_clients() -> list[dict]:
    return call("clients.getClients") or []


def find_client_by_phone(phone: str) -> dict | None:
    want = phone_digits(phone)
    tail = want[-9:]
    for c in get_clients():
        raw = c.get("phone_number") or c.get("phone") or ""
        digits = re.sub(r"\D", "", str(raw))
        if digits == want or digits.endswith(tail):
            return c
    return None


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
        "client_groups_id_client": group_id or POSTER_CLIENT_GROUP_ID,
        "card_number": card_number,
        "phone": normalize_phone(phone),
    }
    if birthday:
        payload["birthday"] = birthday
    if sex is not None:
        payload["client_sex"] = sex
    if bonus_uah:
        payload["bonus"] = to_minor(bonus_uah)
    result = call("clients.createClient", data=payload)
    return int(result)


def update_client(client_id: int | str, **fields) -> Any:
    payload = {"client_id": client_id, **fields}
    return call("clients.updateClient", data=payload)


def set_bonus(client_id: int | str, amount_uah: float) -> Any:
    return update_client(client_id, bonus=to_minor(amount_uah))


def change_client_bonus(client_id: int | str, delta_uah: float) -> Any:
    """Нарахувати (додатнє) або списати (від’ємне) бонуси. Повертає новий баланс."""
    return call(
        "clients.changeClientBonus",
        data={
            "client_id": client_id,
            "count": to_minor(delta_uah),
            "block_webhook": "1",
        },
    )


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


def get_closed_transactions(days: int = 2, spot_id: int | None = None) -> list[dict]:
    """Усі закриті чеки за останні `days` днів."""
    from datetime import datetime, timedelta

    date_to = datetime.now()
    date_from = date_to - timedelta(days=max(1, int(days)))
    params = {
        "dateFrom": date_from.strftime("%Y%m%d"),
        "dateTo": date_to.strftime("%Y%m%d"),
        "include_products": "false",
    }
    if spot_id is not None:
        params["spot_id"] = int(spot_id)
    items = call("dash.getTransactions", params=params) or []
    return [t for t in items if is_transaction_closed(t)]


def transaction_id_from_row(tx: dict) -> str | None:
    raw = tx.get("transaction_id") or tx.get("id") or tx.get("order_id")
    if raw is None or raw == "":
        return None
    return str(raw)


def get_transactions_for_client(client_id: int | str, days: int = 90) -> list[dict]:
    """Закриті чеки клієнта за останні `days` днів."""
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
