"""Агрегована статистика клієнтів і лояльності для адмін-панелі."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from database_functions.db import get_connection
from database_functions.settings_db import get_welcome_bonus_uah

log = logging.getLogger(__name__)

conn = get_connection()
cursor = conn.cursor()


def _since(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _bot_tx_filter() -> str:
    return "telegram_user_id IS NOT NULL"


def get_loyalty_statistics_summary() -> dict:
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

    def period_stats(days: int) -> tuple[int, float, int]:
        r = cursor.execute(
            f"""
            SELECT
                COUNT(*),
                COALESCE(SUM(payed_sum_uah), 0),
                COUNT(DISTINCT telegram_user_id)
            FROM processed_transactions
            WHERE {_bot_tx_filter()} AND processed_at >= ?
            """,
            (_since(days),),
        ).fetchone()
        return int(r[0] or 0), float(r[1] or 0), int(r[2] or 0)

    purchases_today, payed_today, buyers_today = period_stats(1)
    purchases_week, payed_week, buyers_week = period_stats(7)
    purchases_month, payed_month, buyers_month = period_stats(30)

    with_charge = cursor.execute(
        "SELECT COUNT(*) FROM users WHERE registered = 1 AND last_purchase_at IS NOT NULL"
    ).fetchone()[0]

    return {
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
    }


def fetch_poster_bonus_balances() -> dict:
    """
    Сума бонусів на картках клієнтів у Poster (лише зареєстровані в боті).
    При помилці API повертає нулі та error.
    """
    from services import poster

    rows = cursor.execute(
        "SELECT poster_client_id FROM users WHERE registered = 1 AND poster_client_id IS NOT NULL"
    ).fetchall()
    total = 0.0
    with_balance = 0
    errors = 0
    for (cid,) in rows:
        try:
            bal = poster.get_client_bonus_uah(cid)
            total += bal
            if bal > 0:
                with_balance += 1
        except Exception as exc:
            errors += 1
            log.debug("bonus balance client %s: %s", cid, exc)
    return {
        "outstanding_bonus_uah": total,
        "clients_with_bonus_balance": with_balance,
        "poster_errors": errors,
    }
