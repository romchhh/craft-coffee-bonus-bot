from datetime import datetime

from database_functions.db import get_connection

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
            referral_bonus_paid INTEGER DEFAULT 0
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
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
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
):
    cursor.execute(
        """
        UPDATE users SET
            display_name = ?,
            user_phone = ?,
            birthday = ?,
            poster_client_id = ?,
            card_number = ?,
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
            1 if welcome_bonus_given else 0,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_id,
        ),
    )
    conn.commit()


def set_referred_by(user_id: int | str, referrer_user_id: int | None) -> None:
    cursor.execute(
        "UPDATE users SET referred_by_user_id = ?, last_activity = ? WHERE user_id = ?",
        (
            int(referrer_user_id) if referrer_user_id else None,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_id,
        ),
    )
    conn.commit()


def mark_birthday_bonus_given(user_id: int | str) -> None:
    cursor.execute(
        "UPDATE users SET birthday_bonus_given = 1, last_activity = ? WHERE user_id = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id),
    )
    conn.commit()


def mark_referral_bonus_paid(user_id: int | str) -> None:
    cursor.execute(
        "UPDATE users SET referral_bonus_paid = 1, last_activity = ? WHERE user_id = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id),
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


def update_user_birthday(user_id: int | str, birthday: str | None) -> None:
    cursor.execute(
        "UPDATE users SET birthday = ?, last_activity = ? WHERE user_id = ?",
        (
            birthday,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_id,
        ),
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
    """Порядковий номер для EAN-13 на базі max(id) + telegram id хвоста."""
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
