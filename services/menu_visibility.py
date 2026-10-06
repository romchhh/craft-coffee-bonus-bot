"""What to show in the mini-app menu (not everything from Poster)."""
from __future__ import annotations

import re

# Internal / not for guests
EXCLUDED_CATEGORY_IDS = frozenset(
    {
        "42",  # For baristas
        "57",  # Attractions
        "47",  # Cocoa_R
        "48",  # Coffee_R
    }
)

_EXCLUDED_CATEGORY_NAMES = re.compile(
    r"(атракці|для\s*барист|бариста\b|кава_р|какао_р|top\s*screen)",
    re.IGNORECASE,
)

_EXCLUDED_PRODUCT_NAMES = re.compile(
    r"(булочк.*зіпсован|булочк.*на\s*продаж)",
    re.IGNORECASE,
)


def category_visible(category_id: str, category_name: str | None = None) -> bool:
    cid = str(category_id or "").strip()
    if cid in EXCLUDED_CATEGORY_IDS:
        return False
    name = (category_name or "").strip()
    if name and _EXCLUDED_CATEGORY_NAMES.search(name):
        return False
    return True


def product_visible(
    product: dict,
    category_id: str,
    category_name: str | None = None,
) -> bool:
    if not category_visible(category_id, category_name):
        return False
    pname = (product.get("product_name") or "").strip()
    if pname and _EXCLUDED_PRODUCT_NAMES.search(pname):
        return False
    return True
