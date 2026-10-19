"""Craft venue addresses (Brovary) and social links.

Default seed data lives in BRAND_LOCATIONS; runtime data is in spots DB.
"""
from __future__ import annotations

INSTAGRAM_URL = "https://www.instagram.com/kraft_kava_brovary"

CITY = "Бровари, Україна"

# Seed for empty DB (slug → webapp/locations/{slug}.jpg)
BRAND_LOCATIONS: list[dict[str, str]] = [
    {
        "slug": "kraft-1",
        "name": "Крафт 1 · Героїв України 20Б",
        "address": "вул. Героїв України, 20Б",
        "maps_url": "https://maps.app.goo.gl/uLqW75uL4wGXkk9E6",
    },
    {
        "slug": "kraft-2",
        "name": "Крафт 2 · Грушевського",
        "address": "вул. Грушевського, 15",
        "maps_url": (
            "https://www.google.com/maps/search/?api=1"
            "&query=%D0%B2%D1%83%D0%BB.+%D0%9C%D0%B8%D1%85%D0%B0%D0%B9%D0%BB%D0%B0+"
            "%D0%93%D1%80%D1%83%D1%88%D0%B5%D0%B2%D1%81%D1%8C%D0%BA%D0%BE%D0%B3%D0%BE,"
            "+15,+%D0%91%D1%80%D0%BE%D0%B2%D0%B0%D1%80%D0%B8"
        ),
    },
    {
        "slug": "kraft-3",
        "name": "Крафт 3 · Москаленка",
        "address": "вул. Москаленка, 25",
        "maps_url": "https://maps.app.goo.gl/oJTG23wnAgKDNNVD6",
    },
    {
        "slug": "kraft-4",
        "name": "Крафт 4 · Героїв України 16",
        "address": "вул. Героїв України, 16",
        "maps_url": "https://maps.app.goo.gl/4hhHms5wcUkFddy6A",
    },
    {
        "slug": "kraft-5",
        "name": "Крафт 5 · Симоненка",
        "address": "вул. Симоненка, 111",
        "maps_url": "https://maps.app.goo.gl/TgLhB4LixoShWXPf6",
    },
    {
        "slug": "kraft-6",
        "name": "Крафт 6 · Київська",
        "address": "вул. Київська, 150А",
        "maps_url": "https://maps.app.goo.gl/rhg4dd1xDQkNLEZTA",
    },
    {
        "slug": "kraft-7",
        "name": "Крафт 7 · Фіалковського",
        "address": "вул. Фіалковського, 28",
        "maps_url": "https://maps.app.goo.gl/sEYmRRP4nGietVNHA",
    },
    {
        "slug": "zamok",
        "name": "Замок",
        "address": "вул. Героїв Небесної Сотні, 12",
        "maps_url": "https://maps.app.goo.gl/8rrzYUCMwEU4368N8",
    },
    {
        "slug": "karusel",
        "name": "Карусель",
        "address": "Парк Перемоги",
        "maps_url": "https://maps.app.goo.gl/wDoDrRzoWv1WX2Xd7",
    },
]


def _format_address(addr: str) -> str:
    addr = (addr or "").strip()
    if not addr:
        return CITY
    if CITY in addr:
        return addr
    return f"{addr}, {CITY}"


def locations_for_api() -> list[dict]:
    from database_functions import spots_db as spots

    items = []
    for loc in spots.list_spots(active_only=True):
        items.append(
            {
                "id": int(loc["id"]),
                "name": loc.get("name") or "",
                "address": _format_address(str(loc.get("address") or "")),
                "maps_url": loc.get("maps_url") or "",
                "photo_url": spots.photo_url(loc.get("photo_path")),
            }
        )
    return items


def _spot_short_name(name: str) -> str:
    """Drop street suffix after « · » so address is not duplicated in about text."""
    raw = (name or "").strip()
    if " · " in raw:
        return raw.split(" · ", 1)[0].strip() or raw
    return raw


def locations_text_html() -> str:
    from database_functions import spots_db as spots

    lines = ["<b>Шукай нас тут:</b>"]
    for loc in spots.list_spots(active_only=True):
        name = _spot_short_name(str(loc.get("name") or ""))
        addr = (loc.get("address") or "").strip()
        if name and addr:
            lines.append(f"📍 {name}: {addr}")
        elif name or addr:
            lines.append(f"📍 {name or addr}")
    lines.append("")
    lines.append(f'📸 <a href="{INSTAGRAM_URL}">Instagram @kraft_kava_brovary</a>')
    return "\n".join(lines)
