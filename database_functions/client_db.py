from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str

conn = get_connection()
cursor = conn.cursor()


def create_table():
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            user_id NUMERIC UNIQUE,
            user_name TEXT,
            user_first_name TEXT,
            user_last_name TEXT,
            user_phone TEXT,
            language TEXT,
            join_date TEXT,
            last_activity TEXT,
            ref_link INTEGER,
            display_name TEXT,
            birthday TEXT,
            poster_client_id INTEGER,
            card_number TEXT,
            registered INTEGER DEFAULT 0,
            welcome_bonus_given INTEGER DEFAULT 0,
            referred_by_user_id INTEGER,
            birthday_bonus_given INTEGER DEFAULT 0,
            referral_bonus_paid INTEGER DEFAULT 0,
            annual_birthday_year INTEGER,
            birthday_set_at TEXT,
            bonuses_blocked INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    _migrate()


def _migrate():
    cols = {row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}
    additions = {
        "display_name": "TEXT",
        "birthday": "TEXT",
        "poster_client_id": "INTEGER",
        "card_number": "TEXT",
        "registered": "INTEGER DEFAULT 0",
        "welcome_bonus_given": "INTEGER DEFAULT 0",
        "user_phone": "TEXT",
        "referred_by_user_id": "INTEGER",
        "birthday_bonus_given": "INTEGER DEFAULT 0",
        "referral_bonus_paid": "INTEGER DEFAULT 0",
        "annual_birthday_year": "INTEGER",
        "birthday_set_at": "TEXT",
        "referral_click_at": "TEXT",
        # 0 = receives admin broadcasts; 1 = opted out of promotional mailing
        "mailing_opt_out": "INTEGER DEFAULT 0",
        "mailing_opt_out_at": "TEXT",
        # user_opt_out | broadcast_button | admin | bot_blocked | card_deleted
        "mailing_opt_out_reason": "TEXT",
        # Soft mark if loyalty card was removed / wiped (vs mailing opt-out only)
        "card_deleted_at": "TEXT",
        # 1 = cashback / auto Крафтики accrual blocked (admin)
        "bonuses_blocked": "INTEGER DEFAULT 0",
        # When the loyalty card was first issued (fallback: join_date)
        "registered_at": "TEXT",
        # Last time Крафтики were credited (burn clock starts here)
        "last_bonus_accrual_at": "TEXT",
        # Kyiv day we already sent the 7-day burn reminder
        "bonus_expire_reminded_at": "TEXT",
        # Charges credited on charge_visit_day (max 4/day)
        "charges_today": "INTEGER DEFAULT 0",
        # Last confirmed Poster balance (fallback when API down)
        "last_known_bonus": "REAL",
        "last_known_bonus_at": "TEXT",
        # Optional admin-set cashback %; effective = max(personal, charge tier)
        "personal_cashback_percent": "REAL",
    }
    for name, typedef in additions.items():
        if name not in cols:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {name} {typedef}")
    conn.commit()


def add_user(
    user_id,
    user_name,
    user_first_name,
    user_last_name,
    language,
    ref_link: int | None = None,
):
    if get_user(user_id):
        return
    now = kyiv_now_str()
    cursor.execute(
        """
        INSERT INTO users (
            user_id, user_name, user_first_name, user_last_name,
            language, join_date, last_activity, ref_link, registered
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (user_id, user_name, user_first_name, user_last_name, language, now, now, ref_link),
    )
    conn.commit()


def check_user(user_id) -> bool:
    return get_user(user_id) is not None


def get_user(user_id) -> dict | None:
    row = cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def is_registered(user_id) -> bool:
    user = get_user(user_id)
    return bool(user and user.get("registered") and user.get("poster_client_id"))


def update_user_activity(user_id):
    now = kyiv_now_str("%Y-%m-%d %H:%M")
    cursor.execute("UPDATE users SET last_activity = ? WHERE user_id = ?", (now, user_id))
    conn.commit()


def save_registration(
    user_id,
    *,
    display_name: str,
    phone: str,
    birthday: str | None,
    poster_client_id: int,
    card_number: str,
    welcome_bonus_given: bool = True,
    card_short_id: str | None = None,
):
    # Display code under barcode == Poster card_number (same value).
    short = (card_short_id or card_number or "").strip() or None
    now = kyiv_now_str()
    if not get_user(user_id):
        # Edge case: registration without prior /start row — still persist the card.
        cursor.execute(
            """
            INSERT INTO users (
                user_id, user_name, user_first_name, user_last_name, language,
                join_date, last_activity, registered
            ) VALUES (?, NULL, NULL, NULL, NULL, ?, ?, 0)
            """,
            (user_id, now, now),
        )
    cursor.execute(
        """
        UPDATE users SET
            display_name = ?,
            user_phone = ?,
            birthday = ?,
            poster_client_id = ?,
            card_number = ?,
            card_short_id = ?,
            registered = 1,
            welcome_bonus_given = ?,
            registered_at = COALESCE(registered_at, ?),
            last_activity = ?
        WHERE user_id = ?
        """,
        (
            display_name,
            phone,
            birthday,
            poster_client_id,
            card_number,
            short,
            1 if welcome_bonus_given else 0,
            now,
            now,
            user_id,
        ),
    )
    conn.commit()


def welcome_already_given(
    *,
    phone: str | None = None,
    poster_client_id: int | None = None,
) -> bool:
    """True if welcome bonus was already issued for this phone or Poster client."""
    if phone:
        row = cursor.execute(
            "SELECT 1 FROM users WHERE user_phone = ? AND welcome_bonus_given = 1 LIMIT 1",
            (phone,),
        ).fetchone()
        if row:
            return True
    if poster_client_id:
        row = cursor.execute(
            "SELECT 1 FROM users WHERE poster_client_id = ? AND welcome_bonus_given = 1 LIMIT 1",
            (int(poster_client_id),),
        ).fetchone()
        if row:
            return True
    return False


def touch_bonus_accrual(user_id: int | str) -> None:
    """Reset the 90-day burn clock after any Крафтики credit."""
    now = kyiv_now_str()
    cursor.execute(
        """
        UPDATE users SET
            last_bonus_accrual_at = ?,
            bonus_burned_at = NULL,
            bonus_expire_reminded_at = NULL,
            last_activity = ?
        WHERE user_id = ?
        """,
        (now, now, user_id),
    )
    conn.commit()


def mark_bonus_expire_reminded(user_id: int | str) -> None:
    cursor.execute(
        "UPDATE users SET bonus_expire_reminded_at = ? WHERE user_id = ?",
        (kyiv_now_str(), user_id),
    )
    conn.commit()


def card_age_days(user: dict | None) -> int | None:
    """Days since the loyalty card was issued (registered_at → join_date)."""
    if not user:
        return None
    raw = (user.get("registered_at") or user.get("join_date") or "").strip()
    if not raw:
        return None
    from datetime import datetime

    from utils.kyiv_time import KYIV_TZ, now_kyiv

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:19] if len(fmt) > 10 else raw[:10], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KYIV_TZ)
            return max(0, (now_kyiv().date() - dt.date()).days)
        except ValueError:
            continue
    return None


def list_registered_users_for_bonus_jobs() -> list[dict]:
    rows = cursor.execute(
        """
        SELECT * FROM users
        WHERE registered = 1 AND poster_client_id IS NOT NULL
        """
    ).fetchall()
    return [dict(r) for r in rows]


def set_last_known_bonus(user_id: int | str, bonus_uah: float) -> None:
    cursor.execute(
        """
        UPDATE users SET last_known_bonus = ?, last_known_bonus_at = ?, last_activity = ?
        WHERE user_id = ?
        """,
        (round(float(bonus_uah), 2), kyiv_now_str(), kyiv_now_str(), user_id),
    )
    conn.commit()


def set_personal_cashback_percent(user_id: int | str, percent: float | None) -> None:
    cursor.execute(
        """
        UPDATE users SET personal_cashback_percent = ?, last_activity = ?
        WHERE user_id = ?
        """,
        (None if percent is None else float(percent), kyiv_now_str(), user_id),
    )
    conn.commit()


def set_referred_by(user_id: int | str, referrer_user_id: int | None) -> None:
    cursor.execute(
        "UPDATE users SET referred_by_user_id = ?, last_activity = ? WHERE user_id = ?",
        (
            int(referrer_user_id) if referrer_user_id else None,
            kyiv_now_str(),
            user_id,
        ),
    )
    conn.commit()


def set_referred_by_sticky(
    user_id: int | str,
    referrer_user_id: int,
    *,
    ttl_days: int = 30,
) -> bool:
    """First referrer is sticky until ttl_days elapses without registration."""
    from datetime import datetime, timedelta

    from utils.kyiv_time import KYIV_TZ, now_kyiv

    user = get_user(user_id)
    if not user:
        return False

    existing = user.get("referred_by_user_id")
    if existing and user.get("registered"):
        return int(existing) == int(referrer_user_id)

    if existing and not user.get("registered"):
        click_at = user.get("referral_click_at")
        keep = True
        if click_at:
            try:
                started = datetime.strptime(str(click_at)[:19], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=KYIV_TZ
                )
                keep = now_kyiv() - started <= timedelta(days=int(ttl_days))
            except ValueError:
                keep = True
        if keep:
            return int(existing) == int(referrer_user_id)

    now_s = kyiv_now_str()
    cursor.execute(
        """
        UPDATE users SET
            referred_by_user_id = ?,
            referral_click_at = ?,
            last_activity = ?
        WHERE user_id = ?
        """,
        (int(referrer_user_id), now_s, now_s, user_id),
    )
    conn.commit()
    return True


def mark_birthday_bonus_given(user_id: int | str) -> None:
    cursor.execute(
        "UPDATE users SET birthday_bonus_given = 1, last_activity = ? WHERE user_id = ?",
        (kyiv_now_str(), user_id),
    )
    conn.commit()


def claim_birthday_bonus_slot(user_id: int | str) -> bool:
    """Atomically claim one-time birthday bonus. True only for the first caller."""
    cursor.execute(
        """
        UPDATE users
        SET birthday_bonus_given = 1, last_activity = ?
        WHERE user_id = ? AND COALESCE(birthday_bonus_given, 0) = 0
        """,
        (kyiv_now_str(), user_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def clear_birthday_bonus_given(user_id: int | str) -> None:
    cursor.execute(
        "UPDATE users SET birthday_bonus_given = 0, last_activity = ? WHERE user_id = ?",
        (kyiv_now_str(), user_id),
    )
    conn.commit()


def mark_referral_bonus_paid(user_id: int | str) -> None:
    cursor.execute(
        "UPDATE users SET referral_bonus_paid = 1, last_activity = ? WHERE user_id = ?",
        (kyiv_now_str(), user_id),
    )
    conn.commit()


def clear_referral_bonus_paid(user_id: int | str) -> None:
    cursor.execute(
        "UPDATE users SET referral_bonus_paid = 0, last_activity = ? WHERE user_id = ?",
        (kyiv_now_str(), user_id),
    )
    conn.commit()


def mark_annual_birthday_year(user_id: int | str, year: int) -> None:
    cursor.execute(
        "UPDATE users SET annual_birthday_year = ?, last_activity = ? WHERE user_id = ?",
        (int(year), kyiv_now_str(), user_id),
    )
    conn.commit()


def count_successful_referrals(referrer_user_id: int | str) -> int:
    row = cursor.execute(
        """
        SELECT COUNT(*) FROM users
        WHERE referred_by_user_id = ? AND registered = 1 AND referral_bonus_paid = 1
        """,
        (int(referrer_user_id),),
    ).fetchone()
    return int(row[0] or 0)


def update_user_birthday(
    user_id: int | str,
    birthday: str | None,
    *,
    record_set_at: bool = False,
) -> None:
    now = kyiv_now_str()
    if record_set_at:
        cursor.execute(
            "UPDATE users SET birthday = ?, birthday_set_at = ?, last_activity = ? WHERE user_id = ?",
            (birthday, now, now, user_id),
        )
    else:
        cursor.execute(
            "UPDATE users SET birthday = ?, last_activity = ? WHERE user_id = ?",
            (birthday, now, user_id),
        )
    conn.commit()


def registered_poster_client_ids() -> set[int]:
    rows = cursor.execute(
        "SELECT poster_client_id FROM users WHERE registered = 1 AND poster_client_id IS NOT NULL"
    ).fetchall()
    out: set[int] = set()
    for (cid,) in rows:
        try:
            out.add(int(cid))
        except (TypeError, ValueError):
            continue
    return out


def get_user_by_poster_client_id(poster_client_id: int | str) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM users WHERE poster_client_id = ? AND registered = 1",
        (int(poster_client_id),),
    ).fetchone()
    return dict(row) if row else None


def next_card_seq() -> int:
    """Sequential number for EAN-13 based on max(id) + telegram id tail."""
    row = cursor.execute("SELECT COALESCE(MAX(id), 0) FROM users").fetchone()
    base = int(row[0]) + 1
    return 900000 + base


def get_user_id_by_username(username: str):
    cursor.execute("SELECT user_id FROM users WHERE user_name = ?", (username,))
    result = cursor.fetchone()
    return result[0] if result else None


def get_username_by_user_id(user_id: str):
    cursor.execute("SELECT user_name FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None


OPT_OUT_USER = "user_opt_out"
OPT_OUT_BROADCAST = "broadcast_button"
OPT_OUT_ADMIN = "admin"
OPT_OUT_BOT_BLOCKED = "bot_blocked"
OPT_OUT_CARD_DELETED = "card_deleted"

OPT_OUT_REASON_LABELS_UK = {
    OPT_OUT_USER: "Відписка від розсилки",
    OPT_OUT_BROADCAST: "Кнопка в розсилці",
    OPT_OUT_ADMIN: "Адмін",
    OPT_OUT_BOT_BLOCKED: "Заблокував бота",
    OPT_OUT_CARD_DELETED: "Видалив картку",
}


def is_mailing_opted_out(user_id: int | str) -> bool:
    user = get_user(user_id)
    return bool(user and int(user.get("mailing_opt_out") or 0) == 1)


def set_mailing_opt_out(
    user_id: int | str,
    opted_out: bool,
    *,
    reason: str | None = None,
) -> None:
    now = kyiv_now_str()
    if opted_out:
        cursor.execute(
            """
            UPDATE users
            SET mailing_opt_out = 1,
                mailing_opt_out_at = ?,
                mailing_opt_out_reason = ?,
                last_activity = ?
            WHERE user_id = ?
            """,
            (now, reason or OPT_OUT_USER, now, user_id),
        )
    else:
        cursor.execute(
            """
            UPDATE users
            SET mailing_opt_out = 0,
                mailing_opt_out_at = NULL,
                mailing_opt_out_reason = NULL,
                last_activity = ?
            WHERE user_id = ?
            """,
            (now, user_id),
        )
    conn.commit()


def mark_card_deleted(user_id: int | str, *, also_opt_out: bool = True) -> None:
    """Mark loyalty card as removed (distinct from mailing-only opt-out)."""
    now = kyiv_now_str()
    if also_opt_out:
        cursor.execute(
            """
            UPDATE users
            SET card_deleted_at = ?,
                mailing_opt_out = 1,
                mailing_opt_out_at = COALESCE(mailing_opt_out_at, ?),
                mailing_opt_out_reason = ?,
                last_activity = ?
            WHERE user_id = ?
            """,
            (now, now, OPT_OUT_CARD_DELETED, now, user_id),
        )
    else:
        cursor.execute(
            """
            UPDATE users
            SET card_deleted_at = ?, last_activity = ?
            WHERE user_id = ?
            """,
            (now, now, user_id),
        )
    conn.commit()


def count_mailing_opted_out() -> int:
    row = cursor.execute(
        "SELECT COUNT(*) FROM users WHERE COALESCE(mailing_opt_out, 0) = 1"
    ).fetchone()
    return int(row[0] or 0)


def get_mailing_recipient_ids(
    *,
    audience: str = "all",
    spot_names: list[str] | None = None,
    product_qs: list[str] | None = None,
    days_min: int | None = None,
    days_max: int | None = None,
    explicit_ids: list[int] | None = None,
) -> list[int]:
    """Users who still accept promotional broadcasts, optionally filtered.

    audience:
      - all — everyone not opted out (registered preferred)
      - test — admins only
      - segment — filters below (spots OR, products AND, tenure days)
    """
    audience = (audience or "all").strip().lower()
    if audience == "test":
        from database_functions.admin_db import get_all_administrators

        admins = [int(x) for x in (get_all_administrators() or []) if x]
        return sorted(set(admins))

    if explicit_ids is not None:
        ids = [int(x) for x in explicit_ids if x is not None]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = cursor.execute(
            f"""
            SELECT user_id FROM users
            WHERE user_id IN ({placeholders})
              AND COALESCE(mailing_opt_out, 0) = 0
            """,
            ids,
        ).fetchall()
        return [int(r[0]) for r in rows if r[0] is not None]

    spots = [s.strip() for s in (spot_names or []) if s and str(s).strip()]
    products = [p.strip() for p in (product_qs or []) if p and str(p).strip()]
    where = [
        "COALESCE(u.mailing_opt_out, 0) = 0",
        "u.user_id IS NOT NULL",
        "COALESCE(u.registered, 0) = 1",
        "u.card_deleted_at IS NULL",
    ]
    params: list = []

    if spots:
        ph = ",".join("?" * len(spots))
        where.append(
            f"""
            EXISTS (
              SELECT 1 FROM processed_transactions pt
              WHERE pt.telegram_user_id = u.user_id
                AND IFNULL(pt.spot_name, '') IN ({ph})
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

    join_expr = "COALESCE(NULLIF(u.registered_at, ''), NULLIF(u.join_date, ''), '1970-01-01')"
    if days_min is not None:
        where.append(f"(julianday('now', 'localtime') - julianday({join_expr})) >= ?")
        params.append(float(days_min))
    if days_max is not None:
        where.append(f"(julianday('now', 'localtime') - julianday({join_expr})) <= ?")
        params.append(float(days_max))

    sql = f"SELECT u.user_id FROM users u WHERE {' AND '.join(where)}"
    rows = cursor.execute(sql, params).fetchall()
    return [int(r[0]) for r in rows if r[0] is not None]


def is_bonuses_blocked(user_id: int | str) -> bool:
    user = get_user(user_id)
    return bool(user and int(user.get("bonuses_blocked") or 0) == 1)


def set_bonuses_blocked(user_id: int | str, blocked: bool) -> None:
    cursor.execute(
        "UPDATE users SET bonuses_blocked = ?, last_activity = ? WHERE user_id = ?",
        (1 if blocked else 0, kyiv_now_str(), user_id),
    )
    conn.commit()


def count_bonuses_blocked() -> int:
    row = cursor.execute(
        "SELECT COUNT(*) FROM users WHERE COALESCE(bonuses_blocked, 0) = 1"
    ).fetchone()
    return int(row[0] or 0)


def list_recent_registered(limit: int = 25) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT * FROM users
        WHERE registered = 1
        ORDER BY COALESCE(registered_at, join_date, '') DESC, user_id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [dict(r) for r in rows]


def _name_tokens(value: object) -> list[str]:
    import re

    return [t for t in re.split(r"[\s\-_/]+", str(value or "").strip()) if t]


def _name_query_matches(row: dict, query: str) -> bool:
    """Match names by whole words / prefixes — not mid-patronymic (Сергій ⊂ Сергійович)."""
    q = query.lstrip("@").strip().casefold()
    if not q:
        return False

    uname = str(row.get("user_name") or "").lstrip("@").casefold()
    if uname and (uname == q or uname.startswith(q)):
        return True

    # Імʼя / display: слово = запит або починається з нього
    for field in ("display_name", "user_first_name"):
        for word in _name_tokens(row.get(field)):
            w = word.casefold()
            if w == q or w.startswith(q):
                return True

    # Прізвище: лише повний збіг слова (не префікс у по батькові)
    for word in _name_tokens(row.get("user_last_name")):
        if word.casefold() == q:
            return True

    return False


def _name_match_rank(row: dict, query: str) -> int:
    q = query.lstrip("@").strip().casefold()
    first = str(row.get("user_first_name") or "").casefold()
    disp = str(row.get("display_name") or "").casefold()
    if first == q or disp == q:
        return 0
    if first.startswith(q) or disp.startswith(q):
        return 1
    uname = str(row.get("user_name") or "").lstrip("@").casefold()
    if uname == q:
        return 2
    return 3


def search_clients(query: str, *, limit: int = 40) -> list[dict]:
    """Search registered clients by phone, Telegram id, card, username or name."""
    q = (query or "").strip()
    if not q:
        return []
    limit = max(1, min(int(limit), 100))
    digits = "".join(ch for ch in q if ch.isdigit())
    has_letters = any(ch.isalpha() for ch in q)
    looks_like_name = has_letters and not q.lstrip("+").isdigit()

    # --- Name / @username: candidates via LIKE, then precise word filter ---
    if looks_like_name:
        needle = q.lstrip("@").strip()
        like = f"%{needle}%"
        rows = cursor.execute(
            """
            SELECT * FROM users
            WHERE registered = 1 AND (
                IFNULL(user_name, '') LIKE ?
                OR IFNULL(display_name, '') LIKE ?
                OR IFNULL(user_first_name, '') LIKE ?
                OR IFNULL(user_last_name, '') LIKE ?
            )
            LIMIT 300
            """,
            (like, like, like, like),
        ).fetchall()
        matched = [dict(r) for r in rows if _name_query_matches(dict(r), needle)]
        # stable sort: newest activity, then exact-name ranks first
        matched.sort(key=lambda r: str(r.get("last_activity") or ""), reverse=True)
        matched.sort(key=lambda r: _name_match_rank(r, needle))
        return matched[:limit]

    # --- IDs / phone / card / poster ---
    like = f"%{q.lstrip('@')}%"
    params: list = []
    clauses = [
        "CAST(user_id AS TEXT) = ?",
        "CAST(user_id AS TEXT) LIKE ?",
        "card_number LIKE ?",
        "IFNULL(card_short_id, '') LIKE ?",
        "IFNULL(user_name, '') LIKE ?",
        "IFNULL(user_phone, '') LIKE ?",
        "CAST(IFNULL(poster_client_id, '') AS TEXT) = ?",
    ]
    params.extend([q, like, like, like, like, like, q])
    if digits:
        clauses.append(
            "REPLACE(REPLACE(REPLACE(IFNULL(user_phone, ''), '+', ''), ' ', ''), '-', '') LIKE ?"
        )
        params.append(f"%{digits}%")
        if len(digits) >= 3:
            clauses.append("card_number LIKE ?")
            params.append(f"%{digits}%")
            clauses.append("CAST(IFNULL(poster_client_id, '') AS TEXT) LIKE ?")
            params.append(f"%{digits}%")
        if digits == q or (q.isdigit() and len(digits) >= 4):
            clauses.append("CAST(user_id AS TEXT) LIKE ?")
            params.append(f"%{digits}%")

    sql = f"""
        SELECT * FROM users
        WHERE registered = 1 AND ({' OR '.join(clauses)})
        ORDER BY
            CASE WHEN CAST(user_id AS TEXT) = ? THEN 0
                 WHEN card_number = ? THEN 1
                 WHEN IFNULL(user_phone, '') LIKE ? THEN 2
                 ELSE 3 END,
            COALESCE(last_activity, '') DESC
        LIMIT ?
    """
    phone_pref = f"%{digits}%" if digits else like
    params.extend([q, q, phone_pref, limit])
    rows = cursor.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
