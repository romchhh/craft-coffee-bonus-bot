#!/usr/bin/env python3
"""
Тестове онлайн-замовлення в Poster (incomingOrders.createIncomingOrder).

Потрібно: POSTER_TOKEN у .env, pip install requests python-dotenv

Приклади:
  python test_order.py
  python test_order.py --phone 0500000001
  python test_order.py --phone +380502598840 --count 2
  python test_order.py --random-phone --spot-id 1
  python test_order.py --list-spots
  python test_order.py --list-products --spot-id 1

Увага: це **вхідне замовлення** (доставка/сайт), не закритий чек на касі.
Для кешбеку бота чек треба **прийняти й закрити** у Poster (каса / вхідні замовлення).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from services import poster  # noqa: E402

API = "https://joinposter.com/api"
TIMEOUT = 30


def _token() -> str:
    from config import POSTER_TOKEN

    if not POSTER_TOKEN:
        sys.exit("Немає POSTER_TOKEN у .env")
    return POSTER_TOKEN


def api_post(method: str, payload: dict) -> dict:
    """Poster приймає JSON для createIncomingOrder."""
    url = f"{API}/{method}"
    resp = requests.post(url, params={"token": _token()}, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise RuntimeError(json.dumps(body, ensure_ascii=False))
    return body


def pick_spot(spot_id: int | None) -> dict:
    spots = poster.get_spots()
    if not spots:
        sys.exit("Немає точок (access.getSpots).")
    if spot_id is not None:
        for s in spots:
            if int(s.get("spot_id") or 0) == spot_id:
                return s
        sys.exit(f"Точку spot_id={spot_id} не знайдено.")
    return random.choice(spots)


def products_for_spot(spot_id: int) -> list[dict]:
    items = poster.get_products(spot_id)
    out = []
    for p in items:
        if not p.get("product_id"):
            continue
        spots_info = p.get("spots") or []
        if spots_info:
            visible = any(
                int(s.get("spot_id", 0)) == spot_id and str(s.get("visible", "1")) == "1"
                for s in spots_info
            )
            if not visible:
                continue
        out.append(p)
    return out


def pick_product(spot_id: int, product_id: int | None) -> dict:
    visible = products_for_spot(spot_id)
    if not visible:
        sys.exit(f"Немає видимих товарів на точці {spot_id}.")
    if product_id is not None:
        for p in visible:
            if int(p["product_id"]) == product_id:
                return p
        sys.exit(f"product_id={product_id} не знайдено на точці {spot_id}.")
    return random.choice(visible)


def resolve_phone(raw: str | None, random_phone: bool) -> str:
    if random_phone or not raw:
        digits = f"50{random.randint(1000000, 9999999)}"
        return poster.normalize_phone(digits)
    return poster.normalize_phone(raw)


def build_payload(
    *,
    spot_id: int,
    phone: str,
    product_id: int,
    count: int,
    comment: str,
) -> dict:
    return {
        "spot_id": spot_id,
        "phone": phone,
        "products": [{"product_id": product_id, "count": count}],
        "comment": comment,
    }


def create_test_order(
    *,
    phone: str | None = None,
    random_phone: bool = False,
    spot_id: int | None = None,
    product_id: int | None = None,
    count: int = 1,
    comment: str = "TEST Craft Coffee bot order",
) -> dict:
    spot = pick_spot(spot_id)
    sid = int(spot["spot_id"])
    product = pick_product(sid, product_id)
    pid = int(product["product_id"])
    normalized = resolve_phone(phone, random_phone)

    client = poster.find_client_by_phone(normalized)
    if client:
        print(
            f"Клієнт Poster: id={client.get('client_id')} "
            f"картка={client.get('card_number') or '—'} "
            f"група={client.get('client_groups_name')}"
        )
    else:
        print("Клієнт Poster за цим телефоном ще не існує — Poster створить нового.")

    payload = build_payload(
        spot_id=sid,
        phone=normalized,
        product_id=pid,
        count=count,
        comment=comment,
    )

    print("\nЗапит:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(
        f"\nТочка: {spot.get('spot_name')} (id={sid})\n"
        f"Товар: {product.get('product_name')} (id={pid}) × {count}"
    )

    result = api_post("incomingOrders.createIncomingOrder", payload)
    order = result.get("response") or result
    print("\n✅ Замовлення створено:")
    print(json.dumps(order, ensure_ascii=False, indent=2))
    print(
        "\nID:",
        f"incoming_order_id={order.get('incoming_order_id')}",
        f"transaction_id={order.get('transaction_id')}",
        f"client_id={order.get('client_id')}",
        f"status={order.get('status')} (0=нове)",
    )
    return order


def close_incoming_order(order: dict, *, payed_uah: float | None = None) -> dict:
    """Закрити чек після createIncomingOrder (тестовий акаунт)."""
    spot_id = int(order.get("spot_id") or 0)
    tx_id = order.get("transaction_id")
    if not spot_id or not tx_id:
        raise RuntimeError("У замовленні немає spot_id або transaction_id")
    tx = poster.get_transaction(tx_id)
    if not tx:
        raise RuntimeError(f"Чек {tx_id} не знайдено в Poster")
    if poster.is_transaction_closed(tx):
        print(f"Чек {tx_id} уже закритий.")
        return {"transaction_id": tx_id, "already_closed": True}
    sum_minor = int(tx.get("sum") or tx.get("payed_sum") or 0)
    if payed_uah is not None:
        sum_minor = poster.to_minor(payed_uah)
    if sum_minor <= 0:
        sum_minor = poster.to_minor(100)
    print(f"Закриваємо чек {tx_id}, оплата {poster.from_minor(sum_minor):g} грн (копійки={sum_minor})…")
    result = poster.close_transaction(
        spot_id=spot_id,
        transaction_id=tx_id,
        payed_cash=sum_minor,
    )
    print("✅ closeTransaction:", json.dumps(result, ensure_ascii=False))
    return result


def cmd_list_spots() -> None:
    for s in poster.get_spots():
        print(f"  {s.get('spot_id')}: {s.get('spot_name')}")


def cmd_list_products(spot_id: int | None) -> None:
    spots = poster.get_spots() if spot_id is None else [{"spot_id": spot_id}]
    for s in spots:
        sid = int(s["spot_id"])
        print(f"\n=== spot {sid} {s.get('spot_name', '')} ===")
        for p in products_for_spot(sid)[:40]:
            print(f"  {p.get('product_id')}: {p.get('product_name')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Тестове замовлення Poster (incoming order)")
    parser.add_argument("--phone", help="Телефон клієнта (напр. 0500000001)")
    parser.add_argument(
        "--random-phone",
        action="store_true",
        help="Випадковий тестовий номер +38050…",
    )
    parser.add_argument("--spot-id", type=int, help="ID точки Poster")
    parser.add_argument("--product-id", type=int, help="ID товару")
    parser.add_argument("--count", type=int, default=1, help="Кількість (default 1)")
    parser.add_argument("--comment", default="TEST Craft Coffee bot order")
    parser.add_argument("--list-spots", action="store_true")
    parser.add_argument("--list-products", action="store_true")
    parser.add_argument(
        "--close",
        action="store_true",
        help="Після створення закрити чек на касі (для тесту кешбеку)",
    )
    parser.add_argument("--payed-uah", type=float, help="Сума оплати при --close (грн)")
    args = parser.parse_args()

    if args.list_spots:
        cmd_list_spots()
        return
    if args.list_products:
        cmd_list_products(args.spot_id)
        return

    order = create_test_order(
        phone=args.phone,
        random_phone=args.random_phone or not args.phone,
        spot_id=args.spot_id,
        product_id=args.product_id,
        count=max(1, args.count),
        comment=args.comment,
    )
    if args.close:
        close_incoming_order(order, payed_uah=args.payed_uah)


if __name__ == "__main__":
    main()
