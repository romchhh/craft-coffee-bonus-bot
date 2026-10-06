"""All client-facing dates/times use Europe/Kyiv (UTC+2 / +3)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")


def now_kyiv() -> datetime:
    return datetime.now(KYIV_TZ)


def kyiv_now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return now_kyiv().strftime(fmt)
