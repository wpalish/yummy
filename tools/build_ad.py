#!/usr/bin/env python3
"""Монтаж рекламного ролика Yummy из CG-секвенции.

Вход:  ads/cg-sequence.mp4 — пять планов по 2 секунды (Veo, 720x1280)
Выход: ads/yummy-ad.mp4    — 1080x1920, титры, финальная заставка с логотипом

Почему титры рисуем PIL-ом в PNG, а не ffmpeg-овым drawtext: drawtext не умеет
ни переносов, ни разноцветных кусков в строке, ни нормального контроля трекинга,
а кириллицу в нём легко испортить. PNG с альфой даёт полный контроль.

Звук намеренно не кладём: ролик монтируется под трек из редактора Reels,
а сгенерированный эмбиенс там всё равно заглушат.

Запуск: .venv/bin/python tools/build_ad.py
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FPS = 30
SRC = Path("ads/cg-sequence.mp4")
LOGO = Path("app/static/img/logo.png")
OUT = Path("ads/yummy-ad.mp4")

END_SECONDS = 2.6          # финальная заставка
FADE = 0.4                 # переход в заставку — прячет смену фона

INK = (48, 38, 32)
ACCENT = (198, 96, 32)     # оранжевый потемнее палитрного: на беже читается
HALO = (255, 250, 240)

# SF Rounded, а не Arial: в Arial НЕТ глифа тенге (₸ выпадал квадратом-тофу),
# плюс округлые формы ближе к вордмарку Yummy. Шрифт вариативный — вес задаём явно.
FONT_BOLD = "/System/Library/Fonts/SFNSRounded.ttf"
FONT_VARIATION = "Black"


def font(size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT_BOLD, size)
    try:
        f.set_variation_by_name(FONT_VARIATION)
    except Exception:
        pass                      # не вариативный билд — останется дефолтный вес
    return f

# Планы по 2 секунды; титр держим внутри плана, не залезая на склейку.
# (начало, конец, строки) — строка это (текст, цвет, кегль)
TITLES = [
    (0.20, 1.85, [("СЮРПРИЗ-БОКС", INK, 86)]),
    (2.20, 3.85, [("БРОНИРУЙ", INK, 96), ("НА САЙТЕ", INK, 96)]),
    (4.20, 5.85, [("2600 ₸ ЕДЫ", INK, 76), ("ЗА 990 ₸", ACCENT, 104)]),
    (6.20, 7.85, [("ЗАБЕРИ", INK, 96), ("ДО ЗАКРЫТИЯ", INK, 96)]),
    (8.20, 9.90, [("СПАСАЙ ЕДУ", INK, 96)]),
]


def logo_transparent() -> Image.Image:
    """Убрать кремовую подложку логотипа заливкой от углов.

    Именно от углов, а не по всему кадру: внутри вордмарка есть светлая
    обводка-стикер того же оттенка, и глобальный ключ съел бы её вместе с фоном.
    """
    im = Image.open(LOGO).convert("RGBA")
    w, h = im.size
    px = im.load()
    bg = px[1, 1][:3]
    tol = 12

    def near(c) -> bool:
        return all(abs(c[i] - bg[i]) <= tol for i in range(3))

    seen = set()
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


def draw_lines(d: ImageDraw.ImageDraw, lines, top: float, halo: bool = True) -> float:
    """Отрисовать блок строк по центру. Возвращает нижнюю границу блока."""
    y = top
    for text, color, size in lines:
        f = font(size)
        bb = d.textbbox((0, 0), text, font=f)
        x = W / 2 - (bb[2] - bb[0]) / 2 - bb[0]
        if halo:
            # светлый контур: фон CG с градиентом, местами тёмный
            for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)):
                d.text((x + dx, y + dy), text, font=f, fill=HALO)
        d.text((x, y), text, font=f, fill=color)
        y += size * 1.16
    return y


# Экран телефона во втором плане Veo отрисовал пустым белым — так и просили,
# потому что интерфейс он рисует нечитаемой кашей. Код брони кладём сами.
# Границы замерены по кадру построчным сканом, а не на глаз: экран не чисто белый,
# а светло-серый (~218), и по порогу 225 он вообще не находился. Реальная белая
# область — x 394–703 (309 px), первая прикидка «367–735» была шире на 60 px, из-за
# чего подпись упиралась в рамку. Телефон за план смещается на ~14 px — накладка
# статичная, этого не видно.
PHONE = (2.35, 3.80)
SCREEN = (394, 532, 703, 1200)


def make_phone_screen() -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, _ = SCREEN
    cx = (x0 + x1) / 2

    def centered(text: str, size: int, y: float, color) -> None:
        f = font(size)
        bb = d.textbbox((0, 0), text, font=f)
        d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], y), text, font=f, fill=color)

    centered("Бокс забронирован", 24, y0 + 100, (140, 128, 116))
    centered("YM-4K7P", 54, y0 + 138, INK)
    # оранжевая черта под кодом — тот же акцент, что у цены
    d.rounded_rectangle([cx - 78, y0 + 208, cx + 78, y0 + 215], radius=4, fill=ACCENT)
    return img


def make_title(lines) -> Image.Image:
    """Титр в верхней трети: объекты в CG стоят по центру и ниже."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_lines(ImageDraw.Draw(img), lines, top=H * 0.085)
    return img


def make_endcard(logo: Image.Image) -> Image.Image:
    bg = Image.open(LOGO).convert("RGB").getpixel((2, 2))
    img = Image.new("RGB", (W, H), bg)

    lw = int(W * 0.56)
    lh = int(logo.height * lw / logo.width)
    lg = logo.resize((lw, lh), Image.LANCZOS)
    img.paste(lg, (int(W / 2 - lw / 2), int(H * 0.34 - lh / 2)), lg)

    d = ImageDraw.Draw(img)
    y = draw_lines(d, [("Спасай еду", INK, 92)], top=H * 0.52, halo=False)
    draw_lines(d, [("Сюрприз-боксы из пекарен Астаны", ACCENT, 40)],
               top=y + 14, halo=False)
    draw_lines(d, [("wpalish.github.io/yummy", INK, 40)], top=H * 0.72, halo=False)
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

        for i, (_, _, lines) in enumerate(TITLES):
            make_title(lines).save(tmp / f"t{i}.png")
        make_phone_screen().save(tmp / "phone.png")
        end = make_endcard(logo)
        for i in range(int(END_SECONDS * FPS)):
            end.save(tmp / f"e{i:04d}.png")

        # 1. заставка → видео
        endclip = tmp / "end.mp4"
        subprocess.run([
            ff, "-y", "-framerate", str(FPS), "-i", str(tmp / "e%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(endclip),
        ], check=True, capture_output=True)

        # 2. основа: апскейл до 1080x1920 + титры по таймингам
        # порядок входов: экран телефона идёт ПЕРВЫМ слоем — титр должен
        # ложиться поверх него, а не наоборот
        overlays = [(str(tmp / "phone.png"), PHONE)]
        overlays += [(str(tmp / f"t{i}.png"), (a, b))
                     for i, (a, b, _) in enumerate(TITLES)]
        inputs = [ff, "-y", "-i", str(SRC)]
        for path, _ in overlays:
            inputs += ["-i", path]

        chain = [f"[0:v]scale={W}:{H},fps={FPS},format=rgba[base0]"]
        for i, (_, (a, b)) in enumerate(overlays):
            chain.append(
                f"[base{i}][{i+1}:v]overlay=0:0:enable='between(t,{a},{b})'[base{i+1}]"
            )
        chain.append(f"[base{len(overlays)}]format=yuv420p[v]")

        body = tmp / "body.mp4"
        subprocess.run(inputs + [
            "-filter_complex", ";".join(chain), "-map", "[v]",
            "-c:v", "libx264", "-crf", "18", "-an", str(body),
        ], check=True, capture_output=True)

        # 3. склейка с переходом: фон CG с градиентом, жёсткий стык был бы виден
        dur = 10.0
        subprocess.run([
            ff, "-y", "-i", str(body), "-i", str(endclip),
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={FADE}:offset={dur - FADE},"
            f"format=yuv420p[v]",
            "-map", "[v]", "-c:v", "libx264", "-crf", "18",
            "-movflags", "+faststart", "-an", str(OUT),
        ], check=True, capture_output=True)

        print(f"готово: {OUT.resolve()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
