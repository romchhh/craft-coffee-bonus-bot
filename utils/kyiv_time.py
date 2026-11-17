"""All client-facing dates/times use Europe/Kyiv (UTC+2 / +3)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")

_EMPTY = {"", "—", "-", "None", "null", "0000-00-00"}


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


def parse_dt(raw: object) -> datetime | None:
    """Parse common DB / Poster datetime strings (Kyiv wall time, naive)."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None) if raw.tzinfo else raw
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return datetime(raw.year, raw.month, raw.day)
    s = str(raw).strip()
    if not s or s in _EMPTY:
        return None
    s = s.replace("T", " ").replace("/", ".").replace(",", " ")
    # Drop timezone / fractional seconds for display parse
    if "+" in s[10:]:
        s = s.split("+", 1)[0].strip()
    if s.endswith("Z"):
        s = s[:-1].strip()
    if "." in s[10:]:
        s = s.split(".", 1)[0].strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(s[:19] if len(fmt) > 10 else s[:10], fmt)
        except ValueError:
            continue
    return None


def format_dt_ua(
    raw: object,
    *,
    with_time: bool | None = None,
    empty: str = "—",
) -> str:
    """Human date for UI: 13.10.2026 or 13.10.2026 17:24 (Kyiv wall time)."""
    if raw is None:
        return empty
    s = str(raw).strip()
    if not s or s in _EMPTY:
        return empty
    # Already UA-looking date-only
    if with_time is False and len(s) >= 10 and s[2] == "." and s[5] == ".":
        return s[:10]
    dt = parse_dt(raw)
    if not dt:
        return empty
    show_time = with_time
    if show_time is None:
        # Infer: date-only inputs → date-only output
        show_time = not (
            len(s) <= 10
            or (len(s) == 10 and s[4] == "-" and s[7] == "-")
            or (len(s) == 10 and s[2] == "." and s[5] == ".")
        )
        if show_time and dt.hour == 0 and dt.minute == 0 and dt.second == 0:
            # Keep time if original string had a time part
            show_time = ":" in s[10:] if len(s) > 10 else False
    if show_time:
        return dt.strftime("%d.%m.%Y %H:%M")
    return dt.strftime("%d.%m.%Y")


def format_date_ua(raw: object, *, empty: str = "—") -> str:
    """Date only: 13.10.2026."""
    return format_dt_ua(raw, with_time=False, empty=empty)
