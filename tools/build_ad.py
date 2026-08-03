#!/usr/bin/env python3
"""Монтаж рекламного ролика Yummy из CG-секвенции. Премиальная подача.

Вход:  ads/cg-sequence.mp4 — пять планов по 2 секунды (Veo, 720x1280)
Выход: ads/yummy-ad.mp4    — 1080x1920, титры, заставка с логотипом

Чем премиальная подача отличается от первой версии — по убыванию важности:

1. Типографика. Было: жирный округлый SF Rounded крупным кеглем. Стало: SF Pro
   Medium вдвое мельче, капсом, с разрядкой. Дорогая реклама не кричит; крупный
   жирный шрифт читается как распродажа у дороги.
2. Появление. Было: титр возникал рывком. Стало: проявление и уход за 0.35 с.
3. Тень вместо обводки. Обводка по контуру — приём наружной рекламы. Мягкая
   размытая тень отделяет текст от фона, не заявляя о себе.
4. Постоянный вордмарк внизу — бренд присутствует всё время, а не только в конце.
5. Заставка: логотип проявляется, под ним волосяная линия.

Титры рисуем PIL-ом в PNG, а не ffmpeg-овым drawtext: тот не умеет ни разрядки,
ни разноцветных кусков строки, ни мягкой тени, и легко портит кириллицу.

Звук не кладём: ролик монтируется под трек из редактора Reels.

Запуск: .venv/bin/python tools/build_ad.py
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FPS = 30
SRC = Path("ads/cg-sequence.mp4")
LOGO = Path("app/static/img/logo.png")
OUT = Path("ads/yummy-ad.mp4")

BODY_SECONDS = 10.0
END_SECONDS = 3.0
FADE = 0.5                 # переход в заставку: фон CG с градиентом, стык виден
TITLE_FADE = 0.35

INK = (44, 34, 28)
ACCENT = (186, 88, 30)
MUTED = (122, 108, 94)

# SF Pro: есть глиф тенге (в Arial его НЕТ — ₸ выпадал квадратом) и настоящие
# весовые начертания. Medium, а не Black: премиум держится на сдержанности.
FONT = "/System/Library/Fonts/SFNS.ttf"


def font(size: int, weight: str = "Medium") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


# (начало, конец, строки, доля высоты). Строка: (текст, цвет, кегль, вес, разрядка).
# Высота у каждого титра своя: в третьем плане верх занят летящей выпечкой, и
# цена там нечитаема — опускаем её под коробку, где фон чистый.
TITLES = [
    (0.30, 1.80, [("СЮРПРИЗ-БОКС", INK, 46, "Medium", 0.22)], 0.10),
    (2.30, 3.80, [("БРОНИРУЙ НА САЙТЕ", INK, 46, "Medium", 0.22)], 0.10),
    (4.30, 5.80, [("2600 ₸ ЕДЫ", MUTED, 36, "Regular", 0.18),
                  ("ЗА 990 ₸", ACCENT, 92, "Semibold", 0.02)], 0.735),
    (6.30, 7.80, [("ЗАБЕРИ ДО ЗАКРЫТИЯ", INK, 46, "Medium", 0.22)], 0.10),
    (8.30, 9.85, [("СПАСАЙ ЕДУ", INK, 46, "Medium", 0.22)], 0.10),
]

# Экран телефона Veo отрисовал пустым белым (интерфейс он пишет кашей).
# Границы замерены построчным сканом кадра: экран светло-серый (~218), по порогу
# 225 не находился вовсе; реальная область x 394–703, а не 367–735 «на глаз».
PHONE = (2.45, 3.75)
SCREEN = (394, 532, 703, 1200)


def logo_transparent() -> Image.Image:
    """Убрать кремовую подложку логотипа заливкой ОТ УГЛОВ.

    Не глобальным ключом по цвету: внутри вордмарка есть светлая обводка-стикер
    того же оттенка, глобальный ключ съел бы её вместе с фоном.
    """
    im = Image.open(LOGO).convert("RGBA")
    w, h = im.size
    px = im.load()
    bg = px[1, 1][:3]

    def near(c) -> bool:
        return all(abs(c[i] - bg[i]) <= 12 for i in range(3))

    seen: set[tuple[int, int]] = set()
    stack = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    while stack:
        x, y = stack.pop()
        if not (0 <= x < w and 0 <= y < h) or (x, y) in seen:
            continue
        seen.add((x, y))
        if not near(px[x, y]):
            continue
        px[x, y] = (0, 0, 0, 0)
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return im


def tracked_width(d: ImageDraw.ImageDraw, text: str, f, track: float) -> float:
    """Ширина строки с разрядкой: PIL сам её не умеет, считаем посимвольно."""
    return sum(d.textlength(ch, font=f) for ch in text) + track * (len(text) - 1)


def draw_tracked(d: ImageDraw.ImageDraw, text: str, f, track: float,
                 cx: float, y: float, color) -> None:
    x = cx - tracked_width(d, text, f, track) / 2
    for ch in text:
        d.text((x, y), ch, font=f, fill=color)
        x += d.textlength(ch, font=f) + track


def text_block(lines, top: float, shadow: bool = True) -> Image.Image:
    """Блок строк по центру. Тень — отдельным размытым слоем: мягкая тень
    отделяет текст от неровного фона, не превращаясь в обводку."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(img), ImageDraw.Draw(sh)

    y = top
    for text, color, size, weight, track_em in lines:
        f = font(size, weight)
        track = size * track_em
        if shadow:
            draw_tracked(ds, text, f, track, W / 2, y + 3, (60, 44, 30, 90))
        draw_tracked(d, text, f, track, W / 2, y, color)
        y += size * 1.5

    if shadow:
        sh = sh.filter(ImageFilter.GaussianBlur(7))
        img = Image.alpha_composite(sh, img)
    return img


def make_phone_screen() -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, _ = SCREEN
    cx = (x0 + x1) / 2

    f_small = font(22, "Regular")
    draw_tracked(d, "БОКС ЗАБРОНИРОВАН", f_small, 22 * 0.18, cx, y0 + 104, MUTED)
    f_code = font(50, "Semibold")
    draw_tracked(d, "YM-4K7P", f_code, 50 * 0.04, cx, y0 + 146, INK)
    d.rounded_rectangle([cx - 52, y0 + 214, cx + 52, y0 + 217], radius=2, fill=ACCENT)
    return img


def make_wordmark(logo: Image.Image) -> Image.Image:
    """Постоянный вордмарк внизу: бренд присутствует весь ролик, но не спорит
    с едой — потому мелкий и в стороне от титров."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lw = int(W * 0.20)
    lh = int(logo.height * lw / logo.width)
    lg = logo.resize((lw, lh), Image.LANCZOS)
    lg.putalpha(lg.split()[3].point(lambda p: int(p * 0.75)))
    img.paste(lg, (int(W / 2 - lw / 2), int(H * 0.905)), lg)
    return img


def make_endcard(logo: Image.Image) -> Image.Image:
    bg = Image.open(LOGO).convert("RGB").getpixel((2, 2))
    img = Image.new("RGB", (W, H), bg)

    lw = int(W * 0.50)
    lh = int(logo.height * lw / logo.width)
    lg = logo.resize((lw, lh), Image.LANCZOS)
    img.paste(lg, (int(W / 2 - lw / 2), int(H * 0.35 - lh / 2)), lg)

    d = ImageDraw.Draw(img)
    d.rounded_rectangle([W / 2 - 46, H * 0.505, W / 2 + 46, H * 0.505 + 2],
                        radius=1, fill=ACCENT)

    for text, color, size, weight, track_em, y in [
        ("СПАСАЙ ЕДУ", INK, 52, "Semibold", 0.20, H * 0.545),
        ("СЮРПРИЗ-БОКСЫ ИЗ ПЕКАРЕН АСТАНЫ", MUTED, 26, "Regular", 0.20, H * 0.605),
        ("wpalish.github.io/yummy", INK, 30, "Regular", 0.04, H * 0.735),
    ]:
        f = font(size, weight)
        draw_tracked(d, text, f, size * track_em, W / 2, y, color)
    return img


def main() -> None:
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()

    if not SRC.exists():
        raise SystemExit(f"нет исходника: {SRC}")
    OUT.parent.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    try:
        logo = logo_transparent()

        # слои: вордмарк на весь ролик, экран телефона, титры
        layers: list[tuple[Path, float, float]] = []
        p = tmp / "mark.png"
        make_wordmark(logo).save(p)
        layers.append((p, 0.0, BODY_SECONDS))

        p = tmp / "phone.png"
        make_phone_screen().save(p)
        layers.append((p, *PHONE))

        for i, (a, b, lines, top) in enumerate(TITLES):
            p = tmp / f"t{i}.png"
            text_block(lines, top=H * top).save(p)
            layers.append((p, a, b))

        end = make_endcard(logo)
        for i in range(int(END_SECONDS * FPS)):
            end.save(tmp / f"e{i:04d}.png")

        endclip = tmp / "end.mp4"
        subprocess.run([
            ff, "-y", "-framerate", str(FPS), "-i", str(tmp / "e%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", str(endclip),
        ], check=True, capture_output=True)

        # Каждый слой — зациклённая картинка своей длительности с альфа-фейдами,
        # сдвинутая по времени. Иначе титр возникал бы рывком.
        inputs = [ff, "-y", "-i", str(SRC)]
        for path, a, b in layers:
            inputs += ["-loop", "1", "-t", f"{b - a:.2f}", "-i", str(path)]

        chain = [f"[0:v]scale={W}:{H},fps={FPS},format=rgba[base0]"]
        for i, (_, a, b) in enumerate(layers):
            dur = b - a
            fo = max(0.0, dur - TITLE_FADE)
            chain.append(
                f"[{i+1}:v]format=rgba,fps={FPS},"
                f"fade=t=in:st=0:d={TITLE_FADE}:alpha=1,"
                f"fade=t=out:st={fo:.2f}:d={TITLE_FADE}:alpha=1,"
                f"setpts=PTS+{a}/TB[l{i}]"
            )
            chain.append(
                f"[base{i}][l{i}]overlay=0:0:enable='between(t,{a},{b})'[base{i+1}]"
            )
        chain.append(f"[base{len(layers)}]format=yuv420p[v]")

        body = tmp / "body.mp4"
        subprocess.run(inputs + [
            "-filter_complex", ";".join(chain), "-map", "[v]",
            "-c:v", "libx264", "-crf", "16", "-an", str(body),
        ], check=True, capture_output=True)

        subprocess.run([
            ff, "-y", "-i", str(body), "-i", str(endclip),
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={FADE}:"
            f"offset={BODY_SECONDS - FADE},format=yuv420p[v]",
            "-map", "[v]", "-c:v", "libx264", "-crf", "16",
            "-preset", "slow", "-movflags", "+faststart", "-an", str(OUT),
        ], check=True, capture_output=True)

        print(f"готово: {OUT.resolve()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
