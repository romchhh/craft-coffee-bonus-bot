"""Aggregated client/loyalty stats for the admin panel."""
from __future__ import annotations

import logging
import time

from database_functions.db import get_connection
from database_functions.settings_db import get_welcome_bonus_uah
from utils.kyiv_time import kyiv_calendar_start, kyiv_now_str

log = logging.getLogger(__name__)

conn = get_connection()
cursor = conn.cursor()

# Short in-process caches so admin «Статистика» is instant on repeat opens.
_SUMMARY_TTL_SEC = 45.0
_summary_cache: tuple[float, dict] | None = None
_poster_bal_cache: tuple[float, dict] | None = None
_POSTER_BAL_TTL_SEC = 30 * 60.0  # live Poster sweep at most every 30 min


def _bot_tx_filter() -> str:
    return "telegram_user_id IS NOT NULL"


def _tx_when_expr() -> str:
    """Prefer receipt close time over when the bot processed it."""
    return "COALESCE(NULLIF(date_close, ''), processed_at)"


def get_loyalty_statistics_summary(*, force: bool = False) -> dict:
    global _summary_cache
    now = time.monotonic()
    if not force and _summary_cache and now - _summary_cache[0] < _SUMMARY_TTL_SEC:
        return dict(_summary_cache[1])

    registered = cursor.execute(
        "SELECT COUNT(*) FROM users WHERE registered = 1 AND poster_client_id IS NOT NULL"
    ).fetchone()[0]

    welcome_count = cursor.execute(
        "SELECT COUNT(*) FROM users WHERE welcome_bonus_given = 1"
    ).fetchone()[0]
    welcome_uah_per = get_welcome_bonus_uah()
    welcome_total_est = welcome_count * welcome_uah_per

    row = cursor.execute(
        f"""
        SELECT
            COUNT(*) AS purchases,
            COALESCE(SUM(payed_sum_uah), 0),
            COALESCE(SUM(bonus_uah), 0),
            COALESCE(SUM(bonus_spent_uah), 0),
            COUNT(DISTINCT telegram_user_id)
        FROM processed_transactions
        WHERE {_bot_tx_filter()}
        """
    ).fetchone()
    purchases_total = int(row[0] or 0)
    payed_total = float(row[1] or 0)
    cashback_accrued = float(row[2] or 0)
    bonus_spent_total = float(row[3] or 0)
    buyers_unique = int(row[4] or 0)

    returning = cursor.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT telegram_user_id
            FROM processed_transactions
            WHERE {_bot_tx_filter()}
            GROUP BY telegram_user_id
            HAVING COUNT(*) >= 2
        )
        """
    ).fetchone()[0]

    return_rate = (returning / buyers_unique * 100) if buyers_unique > 0 else 0.0

    def period_stats(days_ago_start: int) -> tuple[int, float, int]:
        """Calendar window in Kyiv: from start of (today - days_ago_start) through now."""
        since = kyiv_calendar_start(days_ago_start)
        r = cursor.execute(
            f"""
            SELECT
                COUNT(*),
                COALESCE(SUM(payed_sum_uah), 0),
                COUNT(DISTINCT telegram_user_id)
            FROM processed_transactions
            WHERE {_bot_tx_filter()}
              AND {_tx_when_expr()} >= ?
            """,
            (since,),
        ).fetchone()
        return int(r[0] or 0), float(r[1] or 0), int(r[2] or 0)

    purchases_today, payed_today, buyers_today = period_stats(0)
    purchases_week, payed_week, buyers_week = period_stats(6)
    purchases_month, payed_month, buyers_month = period_stats(29)

    with_charge = cursor.execute(
        "SELECT COUNT(*) FROM users WHERE registered = 1 AND last_purchase_at IS NOT NULL"
    ).fetchone()[0]

    # New loyalty cards today (not every /start)
    new_registered_today = cursor.execute(
        """
        SELECT COUNT(*) FROM users
        WHERE registered = 1
          AND poster_client_id IS NOT NULL
          AND COALESCE(registered_at, join_date) >= ?
        """,
        (kyiv_calendar_start(0),),
    ).fetchone()[0]

    out = {
        "registered_clients": registered,
        "welcome_count": welcome_count,
        "welcome_total_est_uah": welcome_total_est,
        "purchases_total": purchases_total,
        "payed_total_uah": payed_total,
        "cashback_accrued_uah": cashback_accrued,
        "bonus_spent_uah": bonus_spent_total,
        "buyers_unique": buyers_unique,
        "returning_clients": returning,
        "return_rate_percent": return_rate,
        "purchases_today": purchases_today,
        "payed_today_uah": payed_today,
        "buyers_today": buyers_today,
        "purchases_week": purchases_week,
        "payed_week_uah": payed_week,
        "buyers_week": buyers_week,
        "purchases_month": purchases_month,
        "payed_month_uah": payed_month,
        "buyers_month": buyers_month,
        "clients_with_purchase_history": with_charge,
        "new_registered_today": int(new_registered_today or 0),
        "period_note": "календарний день з 00:00 за Києвом",
    }
    _summary_cache = (now, dict(out))
    return out


def fetch_local_bonus_balances() -> dict:
    """Instant sum from last_known_bonus (updated on Mini App / ops) — no Poster."""
    row = cursor.execute(
        """
        SELECT
            COALESCE(SUM(last_known_bonus), 0),
            SUM(CASE WHEN COALESCE(last_known_bonus, 0) > 0 THEN 1 ELSE 0 END),
            SUM(CASE WHEN last_known_bonus IS NULL THEN 1 ELSE 0 END),
            COUNT(*)
        FROM users
        WHERE registered = 1 AND poster_client_id IS NOT NULL
        """
    ).fetchone()
    return {
        "outstanding_bonus_uah": float(row[0] or 0),
        "clients_with_bonus_balance": int(row[1] or 0),
        "clients_unknown_balance": int(row[2] or 0),
        "clients_total": int(row[3] or 0),
        "source": "local",
        "poster_errors": 0,
        "as_of": kyiv_now_str("%d.%m.%Y %H:%M"),
    }


def fetch_poster_bonus_balances(*, force: bool = False) -> dict:
    """
    Slow: live Poster sweep for every registered client.
    Cached 30 min. Prefer fetch_local_bonus_balances() for admin stats.
    Also writes last_known_bonus so the next fast local sum stays accurate.
    """
    global _poster_bal_cache, _summary_cache
    now = time.monotonic()
    if not force and _poster_bal_cache and now - _poster_bal_cache[0] < _POSTER_BAL_TTL_SEC:
        return dict(_poster_bal_cache[1])

    from services import poster

    rows = cursor.execute(
        """
        SELECT user_id, poster_client_id FROM users
        WHERE registered = 1 AND poster_client_id IS NOT NULL
        """
    ).fetchall()
    total = 0.0
    with_balance = 0
    errors = 0
    stamp = kyiv_now_str()
    updates: list[tuple[float, str, str, int]] = []
    for uid, cid in rows:
        try:
            bal = float(poster.get_client_bonus_uah(cid, timeout=4.0))
            total += bal
            if bal > 0:
                with_balance += 1
            updates.append((round(bal, 2), stamp, stamp, int(uid)))
        except Exception as exc:
            errors += 1
            log.debug("bonus balance client %s: %s", cid, exc)
    if updates:
        cursor.executemany(
            """
            UPDATE users
            SET last_known_bonus = ?, last_known_bonus_at = ?, last_activity = ?
            WHERE user_id = ?
            """,
            updates,
        )
        conn.commit()
        _summary_cache = None  # local sum will change
    out = {
        "outstanding_bonus_uah": total,
        "clients_with_bonus_balance": with_balance,
        "clients_unknown_balance": errors,
        "clients_total": len(rows),
        "source": "poster",
        "poster_errors": errors,
        "as_of": kyiv_now_str("%d.%m.%Y %H:%M"),
    }
    _poster_bal_cache = (now, dict(out))
    return out
