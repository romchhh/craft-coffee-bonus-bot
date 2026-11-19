"""Admin client browsing: list, sort, filter, referrals overview."""
from __future__ import annotations

from datetime import date
from typing import Any

from database_functions.db import get_connection

PAGE_SIZE = 10

SORT_LABELS = {
    "join_desc": "Дата реєстрації (новіші)",
    "join_asc": "Дата реєстрації (старіші)",
    "spent_desc": "Витрати (більше → менше)",
    "spent_asc": "Витрати (менше → більше)",
    "bonus_desc": "Нараховані Крафтики",
    "bonus_asc": "Нараховані Крафтики (менше)",
    "age_desc": "Вік (старші)",
    "age_asc": "Вік (молодші)",
    "activity_desc": "Остання активність",
}

SORT_KEYS = list(SORT_LABELS.keys())


def _conn():
    return get_connection()


def _age_years(birthday: str | None, today: date | None = None) -> int | None:
    if not birthday or birthday in ("0000-00-00", ""):
        return None
    try:
        y, m, d = [int(x) for x in str(birthday)[:10].split("-")]
        born = date(y, m, d)
    except (TypeError, ValueError):
        return None
    now = today or date.today()
    age = now.year - born.year - ((now.month, now.day) < (born.month, born.day))
    return age if 0 <= age <= 120 else None


def count_registered() -> int:
    row = _conn().execute(
        "SELECT COUNT(*) FROM users WHERE registered = 1"
    ).fetchone()
    return int(row[0] or 0)


def get_client_admin_details(user_id: int) -> dict[str, Any]:
    """Local purchase / venue / bonus stats for an admin client card."""
    uid = int(user_id)
    row = _conn().execute(
        """
        SELECT
            COALESCE(SUM(payed_sum_uah), 0) AS spent_uah,
            COALESCE(SUM(bonus_uah), 0) AS bonus_earned_uah,
            COALESCE(SUM(bonus_spent_uah), 0) AS bonus_spent_uah,
            COUNT(*) AS purchases_count,
            MAX(COALESCE(NULLIF(date_close, ''), processed_at)) AS last_purchase_at,
            (
                SELECT pt.spot_name FROM processed_transactions pt
                WHERE pt.telegram_user_id = ?
                  AND IFNULL(pt.spot_name, '') != ''
                GROUP BY pt.spot_name
                ORDER BY COUNT(*) DESC
                LIMIT 1
            ) AS top_spot,
            (
                SELECT GROUP_CONCAT(DISTINCT pt.spot_name)
                FROM processed_transactions pt
                WHERE pt.telegram_user_id = ?
                  AND IFNULL(pt.spot_name, '') != ''
            ) AS spots_visited
        FROM processed_transactions
        WHERE telegram_user_id = ?
        """,
        (uid, uid, uid),
    ).fetchone()
    d = dict(row) if row else {}
    return {
        "spent_uah": float(d.get("spent_uah") or 0),
        "bonus_earned_uah": float(d.get("bonus_earned_uah") or 0),
        "bonus_spent_uah": float(d.get("bonus_spent_uah") or 0),
        "purchases_count": int(d.get("purchases_count") or 0),
        "last_purchase_at": d.get("last_purchase_at"),
        "top_spot": d.get("top_spot") or "",
        "spots_visited": d.get("spots_visited") or "",
    }


def enrich_clients_list_metrics(users: list[dict]) -> list[dict]:
    """Attach spent / bonus / age for search & short lists — one batched SQL."""
    if not users:
        return []
    today = date.today()
    ids = [int(u["user_id"]) for u in users]
    placeholders = ",".join("?" * len(ids))
    rows = _conn().execute(
        f"""
        SELECT
            telegram_user_id AS user_id,
            COALESCE(SUM(payed_sum_uah), 0) AS spent_uah,
            COALESCE(SUM(bonus_uah), 0) AS bonus_earned_uah,
            COALESCE(SUM(bonus_spent_uah), 0) AS bonus_spent_uah,
            COUNT(*) AS purchases_count,
            MAX(COALESCE(NULLIF(date_close, ''), processed_at)) AS last_purchase_at
        FROM processed_transactions
        WHERE telegram_user_id IN ({placeholders})
        GROUP BY telegram_user_id
        """,
        ids,
    ).fetchall()
    by_uid = {int(r["user_id"]): dict(r) for r in rows}

    # Top spot per user (single scan, then pick max count in Python)
    spot_rows = _conn().execute(
        f"""
        SELECT telegram_user_id AS user_id, spot_name, COUNT(*) AS cnt
        FROM processed_transactions
        WHERE telegram_user_id IN ({placeholders})
          AND IFNULL(spot_name, '') != ''
        GROUP BY telegram_user_id, spot_name
        """,
        ids,
    ).fetchall()
    top_spot: dict[int, str] = {}
    best_cnt: dict[int, int] = {}
    for r in spot_rows:
        uid = int(r["user_id"])
        cnt = int(r["cnt"] or 0)
        if cnt > best_cnt.get(uid, 0):
            best_cnt[uid] = cnt
            top_spot[uid] = (r["spot_name"] or "").strip()

    out: list[dict] = []
    for u in users:
        d = dict(u)
        uid = int(d["user_id"])
        stats = by_uid.get(uid) or {}
        d["spent_uah"] = float(stats.get("spent_uah") or 0)
        d["bonus_earned_uah"] = float(stats.get("bonus_earned_uah") or 0)
        d["bonus_spent_uah"] = float(stats.get("bonus_spent_uah") or 0)
        d["purchases_count"] = int(stats.get("purchases_count") or 0)
        d["last_purchase_at"] = stats.get("last_purchase_at")
        d["top_spot"] = top_spot.get(uid, "")
        if d.get("age") is None:
            d["age"] = _age_years(d.get("birthday"), today)
        out.append(d)
    return out


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    out: list[str] = []
    for x in value:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def list_clients_sorted(
    sort: str = "join_desc",
    *,
    offset: int = 0,
    limit: int = PAGE_SIZE,
    spot_name: str | list[str] | None = None,
    product_q: str | list[str] | None = None,
    spot_names: list[str] | None = None,
    product_qs: list[str] | None = None,
) -> tuple[list[dict], int]:
    """Return (page rows with metrics, total matching).

    Several spots → OR (купував у будь-якій з обраних).
    Several products → AND (мав кожен із товарів хоча б раз).
    Spot + product filters combine with AND.
    """
    sort = sort if sort in SORT_KEYS else "join_desc"
    offset = max(0, int(offset))
    limit = max(1, min(int(limit), 30))

    spots = _as_str_list(spot_names if spot_names is not None else spot_name)
    products = _as_str_list(product_qs if product_qs is not None else product_q)

    where = ["u.registered = 1"]
    params: list[Any] = []

    if spots:
        placeholders = ",".join("?" * len(spots))
        where.append(
            f"""
            EXISTS (
              SELECT 1 FROM processed_transactions pt
              WHERE pt.telegram_user_id = u.user_id
                AND IFNULL(pt.spot_name, '') IN ({placeholders})
            )
            """
        )
        params.extend(spots)

    for pq in products:
        where.append(
            """
            EXISTS (
              SELECT 1 FROM processed_transactions pt
              WHERE pt.telegram_user_id = u.user_id
                AND IFNULL(pt.products_json, '') LIKE ?
            )
            """
        )
        params.append(f"%{pq}%")

    where_sql = " AND ".join(where)

    age_expr = """
        CASE
          WHEN u.birthday IS NULL OR u.birthday IN ('', '0000-00-00') OR length(u.birthday) < 10 THEN NULL
          ELSE
            CAST(strftime('%Y', 'now') AS INTEGER) - CAST(substr(u.birthday, 1, 4) AS INTEGER)
            - CASE
                WHEN substr('0' || CAST(strftime('%m','now') AS TEXT), -2)
                     || '-' || substr('0' || CAST(strftime('%d','now') AS TEXT), -2)
                     < substr(u.birthday, 6, 5)
                THEN 1 ELSE 0
              END
        END
    """

    order_map = {
        "join_desc": "COALESCE(u.join_date, '') DESC, u.user_id DESC",
        "join_asc": "COALESCE(u.join_date, '') ASC, u.user_id ASC",
        "spent_desc": "spent_uah DESC, COALESCE(u.join_date, '') DESC",
        "spent_asc": "spent_uah ASC, COALESCE(u.join_date, '') DESC",
        "bonus_desc": "bonus_earned_uah DESC, COALESCE(u.join_date, '') DESC",
        "bonus_asc": "bonus_earned_uah ASC, COALESCE(u.join_date, '') DESC",
        "age_desc": "CASE WHEN age_sort IS NULL THEN 1 ELSE 0 END, age_sort DESC, COALESCE(u.join_date, '') DESC",
        "age_asc": "CASE WHEN age_sort IS NULL THEN 1 ELSE 0 END, age_sort ASC, COALESCE(u.join_date, '') DESC",
        "activity_desc": "COALESCE(u.last_activity, '') DESC, u.user_id DESC",
    }
    order_sql = order_map[sort]

    count_sql = f"SELECT COUNT(*) FROM users u WHERE {where_sql}"
    total = int(_conn().execute(count_sql, params).fetchone()[0] or 0)

    sql = f"""
        SELECT
            u.*,
            COALESCE((
                SELECT SUM(pt.payed_sum_uah) FROM processed_transactions pt
                WHERE pt.telegram_user_id = u.user_id
            ), 0) AS spent_uah,
            COALESCE((
                SELECT SUM(pt.bonus_uah) FROM processed_transactions pt
                WHERE pt.telegram_user_id = u.user_id
            ), 0) AS bonus_earned_uah,
            COALESCE((
                SELECT SUM(pt.bonus_spent_uah) FROM processed_transactions pt
                WHERE pt.telegram_user_id = u.user_id
            ), 0) AS bonus_spent_uah,
            (
                SELECT pt.spot_name FROM processed_transactions pt
                WHERE pt.telegram_user_id = u.user_id AND IFNULL(pt.spot_name, '') != ''
                GROUP BY pt.spot_name
                ORDER BY COUNT(*) DESC
                LIMIT 1
            ) AS top_spot,
            ({age_expr}) AS age_sort
        FROM users u
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """
    rows = _conn().execute(sql, [*params, limit, offset]).fetchall()
    out = []
    today = date.today()
    for r in rows:
        d = dict(r)
        d["age"] = _age_years(d.get("birthday"), today)
        if d.get("age") is None and d.get("age_sort") is not None:
            try:
                d["age"] = int(d["age_sort"])
            except (TypeError, ValueError):
                pass
        out.append(d)
    return out, total


def list_visit_spots(*, limit: int = 20) -> list[str]:
    rows = _conn().execute(
        """
        SELECT spot_name, COUNT(*) AS c
        FROM processed_transactions
        WHERE IFNULL(spot_name, '') != '' AND telegram_user_id IS NOT NULL
        GROUP BY spot_name
        ORDER BY c DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [str(r["spot_name"]) for r in rows if r["spot_name"]]


def list_recent_referrals(*, limit: int = 25) -> list[dict]:
    rows = _conn().execute(
        """
        SELECT
            r.*,
            ru.display_name AS referrer_name,
            ru.user_first_name AS referrer_first,
            ru.user_phone AS referrer_phone,
            fu.display_name AS friend_name,
            fu.user_first_name AS friend_first,
            fu.user_phone AS friend_phone
        FROM referrals r
        LEFT JOIN users ru ON ru.user_id = r.referrer_user_id
        LEFT JOIN users fu ON fu.user_id = r.friend_user_id
        ORDER BY COALESCE(r.registered_at, r.created_at, '') DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [dict(r) for r in rows]


def list_friends_of_referrer(referrer_user_id: int, *, limit: int = 30) -> list[dict]:
    rows = _conn().execute(
        """
        SELECT
            r.*,
            u.display_name, u.user_first_name, u.user_phone, u.user_name, u.join_date
        FROM referrals r
        LEFT JOIN users u ON u.user_id = r.friend_user_id
        WHERE r.referrer_user_id = ?
        ORDER BY COALESCE(r.registered_at, r.created_at, '') DESC
        LIMIT ?
        """,
        (int(referrer_user_id), int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def get_referrer_for_friend(friend_user_id: int) -> dict | None:
    row = _conn().execute(
        """
        SELECT
            r.*,
            u.display_name, u.user_first_name, u.user_phone, u.user_name
        FROM referrals r
        LEFT JOIN users u ON u.user_id = r.referrer_user_id
        WHERE r.friend_user_id = ?
        LIMIT 1
        """,
        (int(friend_user_id),),
    ).fetchone()
    return dict(row) if row else None


def iter_clients_stats_for_export() -> list[dict[str, Any]]:
    """All registered clients with spend / bonus / referral / venue stats (local DB)."""
    age_expr = """
        CASE
          WHEN u.birthday IS NULL OR u.birthday IN ('', '0000-00-00') OR length(u.birthday) < 10 THEN NULL
          ELSE
            CAST(strftime('%Y', 'now') AS INTEGER) - CAST(substr(u.birthday, 1, 4) AS INTEGER)
            - CASE
                WHEN substr('0' || CAST(strftime('%m','now') AS TEXT), -2)
                     || '-' || substr('0' || CAST(strftime('%d','now') AS TEXT), -2)
                     < substr(u.birthday, 6, 5)
                THEN 1 ELSE 0
              END
        END
    """
    rows = _conn().execute(
        f"""
        SELECT
            u.user_id,
            u.user_name,
            u.user_first_name,
            u.user_last_name,
            u.display_name,
            u.user_phone,
            u.card_number,
            u.poster_client_id,
            u.birthday,
            ({age_expr}) AS age,
            u.join_date,
            u.last_activity,
            COALESCE(u.bonuses_blocked, 0) AS bonuses_blocked,
            COALESCE(u.welcome_bonus_given, 0) AS welcome_bonus_given,
            COALESCE(u.birthday_bonus_given, 0) AS birthday_bonus_given,
            COALESCE(u.mailing_opt_out, 0) AS mailing_opt_out,
            u.mailing_opt_out_at,
            u.mailing_opt_out_reason,
            u.card_deleted_at,
            u.last_known_bonus,
            u.last_known_bonus_at,
            u.referred_by_user_id,
            COALESCE((
                SELECT SUM(pt.payed_sum_uah) FROM processed_transactions pt
                WHERE pt.telegram_user_id = u.user_id
            ), 0) AS spent_uah,
            COALESCE((
                SELECT COUNT(*) FROM processed_transactions pt
                WHERE pt.telegram_user_id = u.user_id
            ), 0) AS purchases_count,
            COALESCE((
                SELECT SUM(pt.bonus_uah) FROM processed_transactions pt
                WHERE pt.telegram_user_id = u.user_id
            ), 0) AS bonus_earned_uah,
            COALESCE((
                SELECT SUM(pt.bonus_spent_uah) FROM processed_transactions pt
                WHERE pt.telegram_user_id = u.user_id
            ), 0) AS bonus_spent_uah,
            (
                SELECT pt.spot_name FROM processed_transactions pt
                WHERE pt.telegram_user_id = u.user_id AND IFNULL(pt.spot_name, '') != ''
                GROUP BY pt.spot_name
                ORDER BY COUNT(*) DESC
                LIMIT 1
            ) AS top_spot,
            (
                SELECT GROUP_CONCAT(DISTINCT pt.spot_name)
                FROM processed_transactions pt
                WHERE pt.telegram_user_id = u.user_id AND IFNULL(pt.spot_name, '') != ''
            ) AS spots_visited,
            (
                SELECT COUNT(*) FROM referrals r WHERE r.referrer_user_id = u.user_id
            ) AS invited_friends,
            (
                SELECT COUNT(*) FROM referrals r
                WHERE r.referrer_user_id = u.user_id AND r.status = 'paid'
            ) AS invited_paid,
            ref_u.display_name AS referrer_name,
            ref_u.user_first_name AS referrer_first_name,
            ref_u.user_name AS referrer_username,
            ref_u.user_phone AS referrer_phone
        FROM users u
        LEFT JOIN users ref_u ON ref_u.user_id = u.referred_by_user_id
        WHERE u.registered = 1
        ORDER BY COALESCE(u.join_date, '') DESC, u.user_id DESC
        """
    ).fetchall()
    today = date.today()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if d.get("age") is None:
            d["age"] = _age_years(d.get("birthday"), today)
        out.append(d)
    return out
