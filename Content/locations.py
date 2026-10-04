"""Адреси закладів Крафт (Бровари) та соцмережі."""
from __future__ import annotations

from urllib.parse import quote

INSTAGRAM_URL = "https://www.instagram.com/kraft_kava_brovary"

CITY = "Бровари, Україна"

# slug — файл /static/locations/{slug}.jpg (або .webp); lat/lng для маршруту
BRAND_LOCATIONS: list[dict[str, str | float]] = [
    {
        "slug": "simonenka",
        "name": "Симоненка",
        "address": "вул. Симоненка, 111",
        "lat": 50.5172,
        "lng": 30.8015,
    },
    {
        "slug": "heroyiv-20b",
        "name": "Героїв України 20Б",
        "address": "вул. Героїв України, 20Б",
        "lat": 50.5128,
        "lng": 30.7891,
    },
    {
        "slug": "heroyiv-16",
        "name": "Героїв України 16",
        "address": "вул. Героїв України, 16",
        "lat": 50.5135,
        "lng": 30.7876,
    },
    {
        "slug": "moskalenka",
        "name": "Москаленка",
        "address": "вул. Москаленка, 25",
        "lat": 50.5211,
        "lng": 30.7958,
    },
    {
        "slug": "hrushevskoho",
        "name": "Грушевського",
        "address": "вул. Грушевського, 15",
        "lat": 50.5094,
        "lng": 30.7822,
    },
    {
        "slug": "kyivska",
        "name": "Київська",
        "address": "вул. Київська, 150А",
        "lat": 50.5246,
        "lng": 30.8124,
    },
    {
        "slug": "fialkovskoho",
        "name": "Фіалковського",
        "address": "вул. Фіалковського, 28",
        "lat": 50.5189,
        "lng": 30.7765,
    },
]


def maps_url_for(address: str, city: str = CITY, lat: float | None = None, lng: float | None = None) -> str:
    if lat is not None and lng is not None:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    q = quote(f"Крафт кава {city}, {address}")
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def _photo_url(slug: str) -> str:
    return f"/static/locations/{slug}.svg"


def locations_for_api() -> list[dict]:
    items = []
    for i, loc in enumerate(BRAND_LOCATIONS, start=1):
        addr = str(loc["address"])
        slug = str(loc["slug"])
        lat = loc.get("lat")
        lng = loc.get("lng")
        items.append(
            {
                "id": i,
                "slug": slug,
                "name": f"Крафт · {loc['name']}",
                "address": f"{addr}, {CITY}",
                "maps_url": maps_url_for(addr, lat=float(lat) if lat else None, lng=float(lng) if lng else None),
                "photo_url": _photo_url(slug),
                "lat": lat,
                "lng": lng,
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
