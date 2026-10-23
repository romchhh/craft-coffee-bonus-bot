"""Generate a signed Apple Wallet (.pkpass) for Крафт Кава card."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from PIL import Image

from config import (
    APPLE_ORG_NAME,
    APPLE_PASS_CERT,
    APPLE_PASS_KEY,
    APPLE_PASS_KEY_PASSWORD,
    APPLE_PASS_TYPE_ID,
    APPLE_TEAM_ID,
    APPLE_WWDR_CERT,
    WEBAPP_URL,
)

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRAND_LOGO_PATH = PROJECT_ROOT / "webapp" / "assets" / "brand-logo.png"
ASSETS_DIR = PROJECT_ROOT / "webapp" / "wallet_assets"

# Match mini app palette
BRAND_CREAM = (248, 245, 238)  # #F8F5EE
BRAND_INK = (53, 34, 26)  # #35221A
BRAND_SUB = (122, 101, 88)  # #7A6558


def _support_label() -> str:
    try:
        from database_functions.settings_db import get_support_username

        return f"@{get_support_username()}"
    except Exception:
        return WEBAPP_URL or "Крафт Кава"


class AppleWalletError(Exception):
    pass


def is_configured() -> bool:
    return bool(
        APPLE_PASS_TYPE_ID
        and APPLE_TEAM_ID
        and Path(APPLE_PASS_CERT).exists()
        and Path(APPLE_PASS_KEY).exists()
        and Path(APPLE_WWDR_CERT).exists()
    )


def status() -> dict[str, Any]:
    return {
        "configured": is_configured(),
        "pass_type_id": bool(APPLE_PASS_TYPE_ID),
        "team_id": bool(APPLE_TEAM_ID),
        "pass_cert": Path(APPLE_PASS_CERT).exists(),
        "pass_key": Path(APPLE_PASS_KEY).exists(),
        "wwdr_cert": Path(APPLE_WWDR_CERT).exists(),
    }


def _load_key():
    data = Path(APPLE_PASS_KEY).read_bytes()
    password = APPLE_PASS_KEY_PASSWORD.encode() if APPLE_PASS_KEY_PASSWORD else None
    return serialization.load_pem_private_key(data, password=password)


def _load_cert(path: str):
    return x509.load_pem_x509_certificate(Path(path).read_bytes())


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _load_brand_rgba() -> Image.Image:
    if BRAND_LOGO_PATH.is_file():
        return Image.open(BRAND_LOGO_PATH).convert("RGBA")
    raise AppleWalletError(f"Не знайдено логотип: {BRAND_LOGO_PATH}")


def _fit_on_canvas(
    src: Image.Image,
    size: tuple[int, int],
    *,
    bg: tuple[int, int, int] | None = BRAND_CREAM,
    pad: int = 4,
) -> Image.Image:
    w, h = size
    if bg is None:
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    else:
        canvas = Image.new("RGBA", (w, h), (*bg, 255))

    max_w = max(1, w - pad * 2)
    max_h = max(1, h - pad * 2)
    fitted = src.copy()
    fitted.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    x = (w - fitted.width) // 2
    y = (h - fitted.height) // 2
    canvas.alpha_composite(fitted, (x, y))
    return canvas


def _ensure_assets() -> dict[str, bytes]:
    """PassKit images from brand logo (icon + logo @1x/@2x/@3x)."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    src = _load_brand_rgba()

    specs: dict[str, tuple[int, int]] = {
        "icon.png": (29, 29),
        "icon@2x.png": (58, 58),
        "icon@3x.png": (87, 87),
        "logo.png": (160, 50),
        "logo@2x.png": (320, 100),
    }

    files: dict[str, bytes] = {}
    for name, size in specs.items():
        # Logo: transparent on pass cream; icon: small tile on cream.
        bg = None if name.startswith("logo") else BRAND_CREAM
        pad = max(2, min(size) // 12) if not name.startswith("logo") else max(4, min(size) // 16)
        img = _fit_on_canvas(src, size, bg=bg, pad=pad)
        data = _png_bytes(img)
        files[name] = data
        (ASSETS_DIR / name).write_bytes(data)

    return files


def _barcode_alt_text(card_number: str) -> str:
    digits = re.sub(r"\D", "", card_number)
    if len(digits) == 13:
        return f"{digits[0]} {digits[1:7]} {digits[7:13]}"
    if len(digits) == 8:
        return f"{digits[:4]} {digits[4:]}"
    return card_number


def build_pass_json(
    *,
    serial: str,
    name: str,
    card_number: str,
    phone: str | None,
    bonus: float,
) -> dict:
    barcode_format = "PKBarcodeFormatEAN" if len(card_number) == 13 and card_number.isdigit() else "PKBarcodeFormatCode128"
    return {
        "formatVersion": 1,
        "passTypeIdentifier": APPLE_PASS_TYPE_ID,
        "serialNumber": serial,
        "teamIdentifier": APPLE_TEAM_ID,
        "organizationName": APPLE_ORG_NAME,
        "description": "Картка лояльності Крафт Кава",
        "logoText": "",
        "foregroundColor": "rgb(53, 34, 26)",
        "backgroundColor": "rgb(248, 245, 238)",
        "labelColor": "rgb(122, 101, 88)",
        "barcodes": [
            {
                "format": barcode_format,
                "message": card_number,
                "messageEncoding": "iso-8859-1",
                "altText": _barcode_alt_text(card_number),
            }
        ],
        "storeCard": {
            "headerFields": [
                {
                    "key": "bonus",
                    "label": "Крафтики",
                    "value": f"{bonus:g}",
                    "textAlignment": "PKTextAlignmentRight",
                }
            ],
            "primaryFields": [
                {
                    "key": "member",
                    "label": "Власник",
                    "value": name,
                }
            ],
            "secondaryFields": [],
            "auxiliaryFields": [],
            "backFields": [
                {
                    "key": "phone",
                    "label": "Телефон",
                    "value": phone or "—",
                },
                {
                    "key": "info",
                    "label": "Про програму",
                    "value": "1 Крафтик = 1 грн знижки. Покажи штрихкод на касі Крафт Кава.",
                },
                {
                    "key": "support",
                    "label": "Підтримка",
                    "value": _support_label(),
                },
            ],
        },
    }


def create_pkpass(
    *,
    serial: str,
    name: str,
    card_number: str,
    phone: str | None = None,
    bonus: float = 0,
) -> bytes:
    if not is_configured():
        raise AppleWalletError(
            "Apple Wallet не налаштовано: потрібні APPLE_PASS_TYPE_ID, APPLE_TEAM_ID "
            "та сертифікати в папці apple_wallet_certs/"
        )
    if not card_number:
        raise AppleWalletError("Немає номера картки")

    pass_data = build_pass_json(
        serial=serial,
        name=name,
        card_number=card_number,
        phone=phone,
        bonus=bonus,
    )
    files = {"pass.json": json.dumps(pass_data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")}
    files.update(_ensure_assets())

    manifest = {
        name: hashlib.sha1(content).hexdigest()
        for name, content in files.items()
    }
    manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    files["manifest.json"] = manifest_bytes

    cert = _load_cert(APPLE_PASS_CERT)
    key = _load_key()
    wwdr = _load_cert(APPLE_WWDR_CERT)

    signature = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(manifest_bytes)
        .add_signer(cert, key, hashes.SHA256())
        .add_certificate(wwdr)
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
    )
    files["signature"] = signature

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()
