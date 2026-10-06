"""Generate a signed Apple Wallet (.pkpass) for Craft Coffee card."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from PIL import Image, ImageDraw, ImageFont

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

CERTS_DIR = Path("certs")
ASSETS_DIR = Path("webapp/wallet_assets")


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


def _ensure_assets() -> dict[str, bytes]:
    """Minimal PNGs for the pass (icon / logo)."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    files: dict[str, bytes] = {}

    specs = {
        "icon.png": 58,
        "paula.r@example.org": 116,
        "logo.png": (160, 50),
        "paula.r@example.org": (320, 100),
    }

    for name, size in specs.items():
        path = ASSETS_DIR / name
        if path.exists():
            files[name] = path.read_bytes()
            continue

        if isinstance(size, tuple):
            w, h = size
        else:
            w = h = size

        img = Image.new("RGB", (w, h), (28, 20, 16))
        draw = ImageDraw.Draw(img)
        # round cup blot
        margin = max(4, min(w, h) // 8)
        draw.ellipse((margin, margin, w - margin, h - margin), fill=(196, 106, 43))
        # letter K
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", max(14, h // 2))
        except Exception:
            font = ImageFont.load_default()
        text = "K"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((w - tw) / 2, (h - th) / 2 - 2), text, fill=(255, 248, 241), font=font)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        path.write_bytes(data)
        files[name] = data

    return files


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
        "description": "Картка лояльності Craft Coffee",
        "logoText": "Craft Coffee",
        "foregroundColor": "rgb(255, 248, 241)",
        "backgroundColor": "rgb(28, 20, 16)",
        "labelColor": "rgb(240, 163, 90)",
        "barcode": {
            "format": barcode_format,
            "message": card_number,
            "messageEncoding": "iso-8859-1",
            "altText": card_number,
        },
        "barcodes": [
            {
                "format": barcode_format,
                "message": card_number,
                "messageEncoding": "iso-8859-1",
                "altText": card_number,
            }
        ],
        "storeCard": {
            "headerFields": [
                {
                    "key": "bonus",
                    "label": "БОНУСИ",
                    "value": f"{bonus:g} грн",
                }
            ],
            "primaryFields": [],
            "secondaryFields": [
                {
                    "key": "member",
                    "label": "ВЛАСНИК",
                    "value": name,
                }
            ],
            "auxiliaryFields": [
                {
                    "key": "card",
                    "label": "НОМЕР КАРТКИ",
                    "value": card_number,
                }
            ],
            "backFields": [
                {
                    "key": "phone",
                    "label": "Телефон",
                    "value": phone or "—",
                },
                {
                    "key": "info",
                    "label": "Про програму",
                    "value": "1 бонус = 1 грн. Покажи штрихкод на касі Craft Coffee.",
                },
                {
                    "key": "support",
                    "label": "Підтримка",
                    "value": WEBAPP_URL or "Craft Coffee",
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
            "та сертифікати в папці certs/"
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

    # manifest: SHA1 of each file (PassKit requirement)
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
