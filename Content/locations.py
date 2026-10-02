"""Адреси закладів Крафт (Бровари) та соцмережі."""
from __future__ import annotations

from urllib.parse import quote

INSTAGRAM_URL = "https://www.instagram.com/kraft_kava_brovary"

CITY = "Бровари, Україна"

# Назва для картки, повна адреса для відображення
BRAND_LOCATIONS: list[dict[str, str]] = [
    {"name": "Симоненка", "address": "вул. Симоненка, 111"},
    {"name": "Героїв України 20Б", "address": "вул. Героїв України, 20Б"},
    {"name": "Героїв України 16", "address": "вул. Героїв України, 16"},
    {"name": "Москаленка", "address": "вул. Москаленка, 25"},
    {"name": "Грушевського", "address": "вул. Грушевського, 15"},
    {"name": "Київська", "address": "вул. Київська, 150А"},
    {"name": "Фіалковського", "address": "вул. Фіалковського, 28"},
]


def maps_url_for(address: str, city: str = CITY) -> str:
    q = quote(f"Крафт кава {city}, {address}")
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def locations_for_api() -> list[dict]:
    items = []
    for i, loc in enumerate(BRAND_LOCATIONS, start=1):
        addr = loc["address"]
        items.append(
            {
                "id": i,
                "name": f"Крафт · {loc['name']}",
                "address": f"{addr}, {CITY}",
                "maps_url": maps_url_for(addr),
            }
        )
    return items


def locations_text_html() -> str:
    lines = ["<b>Шукай нас тут:</b>"]
    for loc in BRAND_LOCATIONS:
        lines.append(f"📍 {loc['address']}")
    lines.append("")
    lines.append(f'📸 <a href="{INSTAGRAM_URL}">Instagram @kraft_kava_brovary</a>')
    return "\n".join(lines)
