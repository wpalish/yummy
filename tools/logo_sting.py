#!/usr/bin/env python3
"""Брендовая заставка Yummy — анимация настоящего логотипа.

Зачем не через Veo: нейросеть перерисовывает логотип с ошибками (особенно
буквы), а тут нужен точный вордмарк. Собираем кадры сами из
app/static/img/logo.png и кодируем ffmpeg-ом из imageio-ffmpeg — системный
ffmpeg не нужен.

Запуск:  .venv/bin/python tools/logo_sting.py
Выход:   ads/logo-sting.mp4  (1080x1920, 9:16, 3 секунды)
"""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FPS, SECONDS = 30, 3
LOGO = Path("app/static/img/logo.png")
OUT = Path("ads/logo-sting.mp4")

# Палитра сайта (oklch → sRGB), чтобы заставка и сайт были одним продуктом.
# BG берём НЕ из палитры, а пипеткой из самого логотипа: у него непрозрачная
# кремовая подложка, и расхождение даже в 4 пункта даёт видимый прямоугольник
# вокруг вордмарка.
INK = (48, 38, 32)          # --ink, чернильно-коричневый
ACCENT = (214, 122, 60)     # --accent, оранжевый

FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"


def ease_out(t: float) -> float:
    """Замедление к концу — движение читается живым, а не линейным."""
    return 1 - pow(1 - t, 3)


def fade(t: float, start: float, dur: float) -> float:
    """Прозрачность 0→1 на отрезке [start, start+dur] с тем же замедлением."""
    if t < start:
        return 0.0
    return ease_out(min(1.0, (t - start) / dur))


def build_frame(t: float, logo: Image.Image, f_big, f_small,
                BG: tuple[int, int, int]) -> Image.Image:
    frame = Image.new("RGB", (W, H), BG)

    # Логотип: всплывает и слегка увеличивается первые 0.7 с.
    a = fade(t, 0.0, 0.7)
    if a > 0:
        scale = 0.92 + 0.08 * a
        lw = int(W * 0.52 * scale)
        lh = int(logo.height * lw / logo.width)
        lg = logo.resize((lw, lh), Image.LANCZOS)

        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        # лёгкий подъём снизу вверх вместе с проявлением
        y = int(H * 0.40 - lh / 2 + (1 - a) * 40)
        layer.paste(lg, (int(W / 2 - lw / 2), y), lg)
        if a < 1:
            alpha = layer.split()[3].point(lambda p: int(p * a))
            layer.putalpha(alpha)
        frame = Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")

    d = ImageDraw.Draw(frame)

    # Слоган — отдельным текстовым блоком, не разрезая фразу: локаль переводит
    # целыми узлами, да и читается цельная строка лучше.
    a2 = fade(t, 0.6, 0.5)
    if a2 > 0:
        txt = "Спасай еду"
        col = tuple(int(BG[i] + (INK[i] - BG[i]) * a2) for i in range(3))
        bb = d.textbbox((0, 0), txt, font=f_big)
        d.text((W / 2 - (bb[2] - bb[0]) / 2, H * 0.58 + (1 - a2) * 20),
               txt, font=f_big, fill=col)

    a3 = fade(t, 0.95, 0.5)
    if a3 > 0:
        txt = "Сюрприз-боксы из пекарен Астаны"
        col = tuple(int(BG[i] + (ACCENT[i] - BG[i]) * a3) for i in range(3))
        bb = d.textbbox((0, 0), txt, font=f_small)
        d.text((W / 2 - (bb[2] - bb[0]) / 2, H * 0.645 + (1 - a3) * 14),
               txt, font=f_small, fill=col)

    # Мягкая пульсация внизу — кадр не «замерзает» на последней секунде.
    a4 = fade(t, 1.5, 0.6)
    if a4 > 0:
        txt = "wpalish.github.io/yummy"
        k = 0.75 + 0.25 * (0.5 + 0.5 * math.sin(t * 2.2))
        col = tuple(int(BG[i] + (INK[i] - BG[i]) * a4 * k) for i in range(3))
        bb = d.textbbox((0, 0), txt, font=f_small)
        d.text((W / 2 - (bb[2] - bb[0]) / 2, H * 0.80), txt, font=f_small, fill=col)

    return frame


def main() -> None:
    import imageio_ffmpeg

    if not LOGO.exists():
        raise SystemExit(f"нет логотипа: {LOGO}")
    logo = Image.open(LOGO).convert("RGBA")
    # Пипетка по углу: подложка логотипа непрозрачна, и фон кадра обязан
    # совпасть с ней точно, иначе вокруг вордмарка видно прямоугольник.
    bg = Image.open(LOGO).convert("RGB").getpixel((2, 2))
    f_big = ImageFont.truetype(FONT_BOLD, 92)
    f_small = ImageFont.truetype(FONT_REG, 44)

    OUT.parent.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    try:
        total = FPS * SECONDS
        for i in range(total):
            build_frame(i / FPS, logo, f_big, f_small, bg).save(tmp / f"f{i:04d}.png")
        print(f"кадров отрисовано: {total}")

        subprocess.run([
            imageio_ffmpeg.get_ffmpeg_exe(), "-y",
            "-framerate", str(FPS), "-i", str(tmp / "f%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
            "-movflags", "+faststart", str(OUT),
        ], check=True, capture_output=True)
        print(f"готово: {OUT.resolve()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
