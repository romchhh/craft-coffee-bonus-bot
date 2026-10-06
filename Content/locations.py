"""Craft venue addresses (Brovary) and social links."""
from __future__ import annotations

INSTAGRAM_URL = "https://www.instagram.com/kraft_kava_brovary"

CITY = "Бровари, Україна"

# slug = filename under webapp/locations/{slug}.jpg
BRAND_LOCATIONS: list[dict[str, str]] = [
    {
        "slug": "kraft-1",
        "name": "Крафт 1 · Симоненка",
        "address": "вул. Симоненка, 111",
        "maps_url": "https://maps.app.goo.gl/wB1JyPR4M8E15Xbg8",
    },
    {
        "slug": "kraft-2",
        "name": "Крафт 2 · Героїв України 20Б",
        "address": "вул. Героїв України, 20Б",
        "maps_url": "https://maps.app.goo.gl/oJTG23wnAgKDNNVD6",
    },
    {
        "slug": "kraft-3",
        "name": "Крафт 3 · Героїв України 16",
        "address": "вул. Героїв України, 16",
        "maps_url": "https://maps.app.goo.gl/4hhHms5wcUkFddy6A",
    },
    {
        "slug": "kraft-4",
        "name": "Крафт 4 · Москаленка",
        "address": "вул. Москаленка, 25",
        "maps_url": "https://maps.app.goo.gl/TgLhB4LixoShWXPf6",
    },
    {
        "slug": "kraft-5",
        "name": "Крафт 5 · Грушевського",
        "address": "вул. Грушевського, 15",
        "maps_url": "https://maps.app.goo.gl/rhg4dd1xDQkNLEZTA",
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
        "address": "Бровари (див. маршрут у Google Maps)",
        "maps_url": "https://maps.app.goo.gl/8rrzYUCMwEU4368N8",
    },
    {
        "slug": "karusel",
        "name": "Карусель",
        "address": "Бровари (див. маршрут у Google Maps)",
        "maps_url": "https://maps.app.goo.gl/wDoDrRzoWv1WX2Xd7",
    },
]


def _photo_url(slug: str) -> str:
    return f"/static/locations/{slug}.jpg"


def locations_for_api() -> list[dict]:
    items = []
    for i, loc in enumerate(BRAND_LOCATIONS, start=1):
        addr = str(loc["address"])
        slug = str(loc["slug"])
        items.append(
            {
                "id": i,
                "slug": slug,
                "name": loc["name"],
                "address": f"{addr}, {CITY}" if CITY not in addr else addr,
                "maps_url": loc["maps_url"],
                "photo_url": _photo_url(slug),
            }
        )
    return items


def locations_text_html() -> str:
    lines = ["<b>Шукай нас тут:</b>"]
    for loc in BRAND_LOCATIONS:
        lines.append(f"📍 {loc['name']}: {loc['address']}")
    lines.append("")
    lines.append(f'📸 <a href="{INSTAGRAM_URL}">Instagram @kraft_kava_brovary</a>')
    return "\n".join(lines)
