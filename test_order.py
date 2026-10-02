#!/usr/bin/env python3
"""
Створює одне випадкове тестове замовлення в Poster.
Клієнта не вибираємо вручну — Poster лише вимагає телефон у запиті,
тому підставляється випадковий тестовий номер.
Токен: POSTER_TOKEN у .env.  pip install requests
"""
import json
import os
import random
import sys
from pathlib import Path

import requests

API = "https://joinposter.com/api"
TIMEOUT = 20


def load_dotenv() -> None:
    path = Path(".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def call(method: str, data: dict | None = None) -> dict:
    token = os.environ.get("POSTER_TOKEN")
    if not token:
        sys.exit("Немає POSTER_TOKEN у .env")
    url = f"{API}/{method}"
    if data is None:
        resp = requests.get(url, params={"token": token}, timeout=TIMEOUT)
    else:
        resp = requests.post(url, params={"token": token}, json=data, timeout=TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        sys.exit(f"Помилка Poster: {json.dumps(body, ensure_ascii=False)}")
    return body


def main() -> None:
    load_dotenv()

    spots = call("access.getSpots").get("response") or []
    if not spots:
        sys.exit("Немає точок (spots).")
    spot = random.choice(spots)
    spot_id = int(spot["spot_id"])

    products = call("menu.getProducts").get("response") or []
    visible = []
    for p in products:
        spots_info = p.get("spots") or []
        ok = any(
            int(s.get("spot_id", 0)) == spot_id and str(s.get("visible", "1")) == "1"
            for s in spots_info
        ) if spots_info else True
        if ok and p.get("product_id"):
            visible.append(p)
    if not visible:
        sys.exit(f"Немає товарів на точці {spot_id}.")

    product = random.choice(visible)
    product_id = int(product["product_id"])
    count = random.randint(1, 3)
    # Poster вимагає phone; клієнта не передаємо — лише тестовий номер
    phone = f"+38050{random.randint(1000000, 9999999)}"

    payload = {
        "spot_id": spot_id,
        "phone": phone,
        "products": [{"product_id": product_id, "count": count}],
        "comment": "TEST random order",
    }

    print("Створюю замовлення:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"товар: {product.get('product_name')} (id={product_id})")
    print(f"точка: {spot.get('spot_name')} (id={spot_id})")

    result = call("incomingOrders.createIncomingOrder", payload)
    print("\nВідповідь Poster:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
