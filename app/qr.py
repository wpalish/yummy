"""Генерация QR-кода выдачи (SVG) локально, без внешних сервисов."""
from __future__ import annotations

import io

import segno


def qr_svg(data: str, scale: int = 4) -> str:
    """Вернуть инлайн-SVG QR-кода для строки (код выдачи заказа)."""
    buf = io.BytesIO()
    segno.make(data, error="m").save(
        buf, kind="svg", scale=scale, border=2, dark="#1b2a1f",
        light=None, xmldecl=False, svgns=True
    )
    return buf.getvalue().decode("utf-8").replace("\n", "").replace("\r", "")
