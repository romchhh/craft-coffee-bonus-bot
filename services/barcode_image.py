"""PNG штрихкод картки для повідомлень у Telegram."""
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
