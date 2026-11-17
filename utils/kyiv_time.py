"""All client-facing dates/times use Europe/Kyiv (UTC+2 / +3)."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")


def now_kyiv() -> datetime:
    return datetime.now(KYIV_TZ)


def kyiv_now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return now_kyiv().strftime(fmt)


def kyiv_calendar_start(days_ago: int = 0) -> str:
    """Start of a Kyiv calendar day as 'YYYY-MM-DD HH:MM:SS' (naive local Kyiv wall time).

    days_ago=0 → today 00:00 Kyiv; days_ago=6 → start of the day 6 days ago
    (7 calendar days including today).
    """
    d = now_kyiv().date() - timedelta(days=int(days_ago))
    return f"{d.isoformat()} 00:00:00"
