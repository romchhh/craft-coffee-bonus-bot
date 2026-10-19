"""Detect suspicious loyalty patterns for admin review."""
from __future__ import annotations

from database_functions.db import get_connection
from utils.kyiv_time import now_kyiv

conn = get_connection()


def _since(days: int = 0, hours: int = 0) -> str:
    from datetime import timedelta

    return (now_kyiv() - timedelta(days=days, hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def frequent_cashback(*, hours: int = 24, min_count: int = 4) -> list[dict]:
    """Clients with many cashback accruals in a short window."""
    rows = conn.execute(
        """
        SELECT telegram_user_id AS user_id,
               COUNT(*) AS cnt,
               ROUND(SUM(bonus_uah), 2) AS total_bonus,
               ROUND(SUM(payed_sum_uah), 2) AS total_payed
        FROM processed_transactions
        WHERE telegram_user_id IS NOT NULL
          AND bonus_uah > 0
          AND processed_at >= ?
        GROUP BY telegram_user_id
        HAVING COUNT(*) >= ?
        ORDER BY cnt DESC, total_bonus DESC
        LIMIT 15
        """,
        (_since(hours=hours), int(min_count)),
    ).fetchall()
    return [dict(r) for r in rows]


def high_cashback_week(*, min_uah: float = 80.0) -> list[dict]:
    rows = conn.execute(
        """
        SELECT telegram_user_id AS user_id,
               COUNT(*) AS cnt,
               ROUND(SUM(bonus_uah), 2) AS total_bonus,
               ROUND(SUM(payed_sum_uah), 2) AS total_payed
        FROM processed_transactions
        WHERE telegram_user_id IS NOT NULL
          AND bonus_uah > 0
          AND processed_at >= ?
        GROUP BY telegram_user_id
        HAVING SUM(bonus_uah) >= ?
        ORDER BY total_bonus DESC
        LIMIT 15
        """,
        (_since(days=7), float(min_uah)),
    ).fetchall()
    return [dict(r) for r in rows]


def micro_checks(*, hours: int = 24, max_payed: float = 55.0, min_count: int = 5) -> list[dict]:
    """Many near-minimum checks (possible Заряд / cashback farm)."""
    rows = conn.execute(
        """
        SELECT telegram_user_id AS user_id,
               COUNT(*) AS cnt,
               ROUND(SUM(payed_sum_uah), 2) AS total_payed,
               ROUND(SUM(bonus_uah), 2) AS total_bonus
        FROM processed_transactions
        WHERE telegram_user_id IS NOT NULL
          AND payed_sum_uah > 0
          AND payed_sum_uah <= ?
          AND processed_at >= ?
        GROUP BY telegram_user_id
        HAVING COUNT(*) >= ?
        ORDER BY cnt DESC
        LIMIT 15
        """,
        (float(max_payed), _since(hours=hours), int(min_count)),
    ).fetchall()
    return [dict(r) for r in rows]


def busy_referrers(*, days: int = 7, min_count: int = 3) -> list[dict]:
    rows = conn.execute(
        """
        SELECT referrer_user_id AS user_id,
               COUNT(*) AS cnt,
               SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid_cnt,
               SUM(CASE WHEN status = 'owner_review' THEN 1 ELSE 0 END) AS review_cnt,
               ROUND(SUM(CASE WHEN status = 'paid' THEN amount_uah ELSE 0 END), 2) AS paid_uah
        FROM referrals
        WHERE COALESCE(registered_at, created_at, '') >= ?
        GROUP BY referrer_user_id
        HAVING COUNT(*) >= ?
        ORDER BY cnt DESC
        LIMIT 15
        """,
        (_since(days=days), int(min_count)),
    ).fetchall()
    return [dict(r) for r in rows]


def enrich_with_users(rows: list[dict]) -> list[dict]:
    from database_functions.client_db import get_user

    out = []
    for r in rows:
        uid = r.get("user_id")
        u = get_user(uid) if uid else None
        item = dict(r)
        if u:
            item["name"] = (
                u.get("display_name")
                or u.get("user_first_name")
                or str(uid)
            )
            item["phone"] = u.get("user_phone") or ""
            item["blocked"] = bool(int(u.get("bonuses_blocked") or 0))
            item["card"] = u.get("card_number") or ""
        else:
            item["name"] = str(uid or "—")
            item["phone"] = ""
            item["blocked"] = False
            item["card"] = ""
        out.append(item)
    return out


def build_anomalies_report() -> str:
    lines = ["⚠️ <b>Аномалії лояльності</b>\n"]

    freq = enrich_with_users(frequent_cashback(hours=24, min_count=4))
    lines.append("<b>Часті нарахування кешбеку (24 год, ≥4)</b>")
    if not freq:
        lines.append("· немає")
    else:
        for r in freq:
            flag = "🚫 " if r["blocked"] else ""
            lines.append(
                f"· {flag}<b>{_esc(r['name'])}</b> · id <code>{r['user_id']}</code> · "
                f"{r['cnt']}× · +{r['total_bonus']:g} · чеки {r['total_payed']:g} грн"
            )

    week = enrich_with_users(high_cashback_week(min_uah=80))
    lines.append("\n<b>Багато кешбеку за 7 днів (≥80)</b>")
    if not week:
        lines.append("· немає")
    else:
        for r in week:
            flag = "🚫 " if r["blocked"] else ""
            lines.append(
                f"· {flag}<b>{_esc(r['name'])}</b> · <code>{r['user_id']}</code> · "
                f"+{r['total_bonus']:g} ({r['cnt']} чеків)"
            )

    micro = enrich_with_users(micro_checks(hours=24, max_payed=55, min_count=5))
    lines.append("\n<b>Часті малі чеки ≤55 грн (24 год, ≥5)</b>")
    if not micro:
        lines.append("· немає")
    else:
        for r in micro:
            flag = "🚫 " if r["blocked"] else ""
            lines.append(
                f"· {flag}<b>{_esc(r['name'])}</b> · <code>{r['user_id']}</code> · "
                f"{r['cnt']}× · сума {r['total_payed']:g}"
            )

    refs = enrich_with_users(busy_referrers(days=7, min_count=3))
    lines.append("\n<b>Активні реферери (7 днів, ≥3 друзів)</b>")
    if not refs:
        lines.append("· немає")
    else:
        for r in refs:
            flag = "🚫 " if r["blocked"] else ""
            lines.append(
                f"· {flag}<b>{_esc(r['name'])}</b> · <code>{r['user_id']}</code> · "
                f"друзів {r['cnt']} · paid {r['paid_cnt']} · review {r['review_cnt']}"
            )

    lines.append(
        "\n<i>Натисни клієнта в «👤 Клієнти» за Telegram ID, щоб переглянути картку / "
        "заблокувати Крафтики.</i>"
    )
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n…"
    return text


def _esc(s: object) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
