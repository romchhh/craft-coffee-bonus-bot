"""PNG card barcode for Telegram messages."""
from __future__ import annotations

from io import BytesIO


def render_card_barcode_png(card_number: str) -> BytesIO:
    import barcode
    from barcode.writer import ImageWriter

    digits = "".join(c for c in (card_number or "") if c.isdigit())
    if len(digits) == 13:
        code_class = barcode.get_barcode_class("ean13")
        payload = digits[:12]
    elif digits:
        code_class = barcode.get_barcode_class("code128")
        payload = card_number.strip()
    else:
        raise ValueError("empty card number")

    buf = BytesIO()
    writer = ImageWriter()
    code_class(payload, writer=writer).write(
        buf,
        options={
            "module_width": 0.32,
            "module_height": 14.0,
            "font_size": 11,
            "text_distance": 5.0,
            "quiet_zone": 3.0,
            "dpi": 300,
        },
    )
    buf.seek(0)
    return buf


def render_wallet_strip_barcode_png(
    card_number: str,
    *,
    width: int,
    height: int,
    foreground: tuple[int, int, int] = (53, 34, 26),
    background: tuple[int, int, int] = (248, 245, 238),
) -> BytesIO:
    """Large barcode for Apple Wallet strip (no caption)."""
    import barcode
    from barcode.writer import ImageWriter
    from PIL import Image

    digits = "".join(c for c in (card_number or "") if c.isdigit())
    if len(digits) == 13:
        code_class = barcode.get_barcode_class("ean13")
        payload = digits[:12]
    elif digits:
        code_class = barcode.get_barcode_class("code128")
        payload = card_number.strip()
    else:
        raise ValueError("empty card number")

    module_height = max(18.0, height * 0.42)
    module_width = max(0.22, (width * 0.9) / 220.0)
    raw = BytesIO()
    code_class(payload, writer=ImageWriter()).write(
        raw,
        options={
            "module_width": module_width,
            "module_height": module_height,
            "font_size": 0,
            "text_distance": 0,
            "quiet_zone": 2.0,
            "write_text": False,
            "dpi": 300,
            "foreground": foreground,
            "background": background,
        },
    )
    raw.seek(0)
    code_img = Image.open(raw).convert("RGBA")
    canvas = Image.new("RGBA", (width, height), (*background, 255))
    pad_x = max(8, int(width * 0.04))
    pad_y = max(6, int(height * 0.08))
    max_w = width - pad_x * 2
    max_h = height - pad_y * 2
    scale = min(max_w / code_img.width, max_h / code_img.height, 1.0)
    if scale < 1.0:
        code_img = code_img.resize(
            (max(1, int(code_img.width * scale)), max(1, int(code_img.height * scale))),
            Image.Resampling.LANCZOS,
        )
    x = (width - code_img.width) // 2
    y = (height - code_img.height) // 2
    canvas.alpha_composite(code_img, (x, y))
    out = BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out
