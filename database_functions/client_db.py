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
        # 1 = cashback / auto Крафтики accrual blocked (admin)
        "bonuses_blocked": "INTEGER DEFAULT 0",
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
            kyiv_now_str(),
            user_id,
        ),
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


def is_mailing_opted_out(user_id: int | str) -> bool:
    user = get_user(user_id)
    return bool(user and int(user.get("mailing_opt_out") or 0) == 1)


def set_mailing_opt_out(user_id: int | str, opted_out: bool) -> None:
    cursor.execute(
        "UPDATE users SET mailing_opt_out = ?, last_activity = ? WHERE user_id = ?",
        (1 if opted_out else 0, kyiv_now_str(), user_id),
    )
    conn.commit()


def count_mailing_opted_out() -> int:
    row = cursor.execute(
        "SELECT COUNT(*) FROM users WHERE COALESCE(mailing_opt_out, 0) = 1"
    ).fetchone()
    return int(row[0] or 0)


def get_mailing_recipient_ids() -> list[int]:
    """Users who still accept promotional bot broadcasts."""
    rows = cursor.execute(
        """
        SELECT user_id FROM users
        WHERE COALESCE(mailing_opt_out, 0) = 0
          AND user_id IS NOT NULL
        """
    ).fetchall()
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


def list_recent_registered(limit: int = 12) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT * FROM users
        WHERE registered = 1
        ORDER BY COALESCE(join_date, '') DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [dict(r) for r in rows]


def search_clients(query: str, *, limit: int = 15) -> list[dict]:
    """Search registered clients by phone, Telegram id, card, username or name."""
    q = (query or "").strip()
    if not q:
        return []
    digits = "".join(ch for ch in q if ch.isdigit())
    like = f"%{q.lstrip('@')}%"
    params: list = []
    clauses = [
        "CAST(user_id AS TEXT) = ?",
        "card_number LIKE ?",
        "IFNULL(card_short_id, '') LIKE ?",
        "IFNULL(user_name, '') LIKE ?",
        "IFNULL(display_name, '') LIKE ?",
        "IFNULL(user_first_name, '') LIKE ?",
        "IFNULL(user_last_name, '') LIKE ?",
        "IFNULL(user_phone, '') LIKE ?",
    ]
    params.extend(
        [
            q,
            like,
            like,
            like,
            like,
            like,
            like,
            like,
        ]
    )
    if digits:
        clauses.append("REPLACE(REPLACE(IFNULL(user_phone, ''), '+', ''), ' ', '') LIKE ?")
        params.append(f"%{digits}%")
        if len(digits) >= 4:
            clauses.append("card_number LIKE ?")
            params.append(f"%{digits}%")
        if digits == q or (q.isdigit() and len(digits) >= 5):
            clauses.append("CAST(user_id AS TEXT) LIKE ?")
            params.append(f"%{digits}%")

    sql = f"""
        SELECT * FROM users
        WHERE registered = 1 AND ({' OR '.join(clauses)})
        ORDER BY COALESCE(last_activity, '') DESC
        LIMIT ?
    """
    params.append(int(limit))
    rows = cursor.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
