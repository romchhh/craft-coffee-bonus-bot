"""Apple Wallet pass registrations (PassKit web service)."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str
from config import APPLE_WALLET_SECRET

conn = get_connection()
cursor = conn.cursor()


def create_wallet_passes_tables() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS apple_wallet_passes (
            serial_number TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            auth_token TEXT NOT NULL,
            updated_tag TEXT NOT NULL,
            updated_at TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS apple_wallet_registrations (
            id INTEGER PRIMARY KEY,
            device_library_id TEXT NOT NULL,
            push_token TEXT NOT NULL,
            pass_type_id TEXT NOT NULL,
            serial_number TEXT NOT NULL,
            user_id INTEGER,
            registered_at TEXT,
            UNIQUE(device_library_id, pass_type_id, serial_number)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_apple_wallet_reg_serial
        ON apple_wallet_registrations(serial_number)
        """
    )
    conn.commit()


def serial_for_user(user: dict) -> str:
    cid = user.get("poster_client_id") or user.get("user_id")
    card = (user.get("card_number") or "").strip()
    return f"craft-{cid}-{card}"


def auth_token_for_serial(serial: str) -> str:
    """Stable per-serial token derived from secret (also stored in DB)."""
    digest = hmac.new(
        APPLE_WALLET_SECRET.encode(),
        f"apple-pass:{serial}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest[:32]


def ensure_pass_record(user_id: int, serial: str) -> dict:
    row = cursor.execute(
        "SELECT * FROM apple_wallet_passes WHERE serial_number = ?",
        (serial,),
    ).fetchone()
    if row:
        return dict(row)
    now = kyiv_now_str()
    tag = now.replace(" ", "T")
    token = auth_token_for_serial(serial)
    cursor.execute(
        """
        INSERT INTO apple_wallet_passes (serial_number, user_id, auth_token, updated_tag, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (serial, int(user_id), token, tag, now),
    )
    conn.commit()
    return {
        "serial_number": serial,
        "user_id": int(user_id),
        "auth_token": token,
        "updated_tag": tag,
        "updated_at": now,
    }


def get_pass_by_serial(serial: str) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM apple_wallet_passes WHERE serial_number = ?",
        (serial,),
    ).fetchone()
    return dict(row) if row else None


def get_pass_by_user_id(user_id: int) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM apple_wallet_passes WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
        (int(user_id),),
    ).fetchone()
    return dict(row) if row else None


def bump_pass_updated(serial: str) -> str:
    now = kyiv_now_str()
    tag = now.replace(" ", "T") + f".{secrets.token_hex(2)}"
    cursor.execute(
        """
        UPDATE apple_wallet_passes
        SET updated_tag = ?, updated_at = ?
        WHERE serial_number = ?
        """,
        (tag, now, serial),
    )
    if cursor.rowcount == 0:
        conn.commit()
        return tag
    conn.commit()
    return tag


def register_device(
    *,
    device_library_id: str,
    push_token: str,
    pass_type_id: str,
    serial_number: str,
    user_id: int | None,
) -> bool:
    """Returns True if newly registered, False if already existed (token updated)."""
    existing = cursor.execute(
        """
        SELECT id, push_token FROM apple_wallet_registrations
        WHERE device_library_id = ? AND pass_type_id = ? AND serial_number = ?
        """,
        (device_library_id, pass_type_id, serial_number),
    ).fetchone()
    now = kyiv_now_str()
    if existing:
        cursor.execute(
            """
            UPDATE apple_wallet_registrations
            SET push_token = ?, user_id = COALESCE(?, user_id), registered_at = ?
            WHERE id = ?
            """,
            (push_token, user_id, now, existing["id"]),
        )
        conn.commit()
        return False
    cursor.execute(
        """
        INSERT INTO apple_wallet_registrations (
            device_library_id, push_token, pass_type_id, serial_number, user_id, registered_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (device_library_id, push_token, pass_type_id, serial_number, user_id, now),
    )
    conn.commit()
    return True


def unregister_device(
    *,
    device_library_id: str,
    pass_type_id: str,
    serial_number: str,
) -> None:
    cursor.execute(
        """
        DELETE FROM apple_wallet_registrations
        WHERE device_library_id = ? AND pass_type_id = ? AND serial_number = ?
        """,
        (device_library_id, pass_type_id, serial_number),
    )
    conn.commit()


def list_serials_for_device(
    device_library_id: str,
    pass_type_id: str,
    *,
    passes_updated_since: str | None = None,
) -> list[str]:
    rows = cursor.execute(
        """
        SELECT r.serial_number, p.updated_tag
        FROM apple_wallet_registrations r
        JOIN apple_wallet_passes p ON p.serial_number = r.serial_number
        WHERE r.device_library_id = ? AND r.pass_type_id = ?
        """,
        (device_library_id, pass_type_id),
    ).fetchall()
    out: list[str] = []
    for row in rows:
        if passes_updated_since and (row["updated_tag"] or "") <= passes_updated_since:
            continue
        out.append(row["serial_number"])
    return out


def push_tokens_for_serial(serial: str) -> list[str]:
    rows = cursor.execute(
        """
        SELECT DISTINCT push_token FROM apple_wallet_registrations
        WHERE serial_number = ? AND push_token IS NOT NULL AND push_token != ''
        """,
        (serial,),
    ).fetchall()
    return [str(r["push_token"]) for r in rows]
