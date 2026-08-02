#!/usr/bin/env python3
"""Генерация рекламных роликов Yummy через Google Veo.

Зачем отдельный скрипт, а не разовый вызов: ролики платные и генерируются
минутами. Нужно видеть смету ДО списания денег, уметь прогнать вхолостую и не
терять уже сгенерированное при обрыве.

Запуск:
    export GEMINI_API_KEY=...
    .venv/bin/python tools/veo_ads.py --list          # что за ролики
    .venv/bin/python tools/veo_ads.py --dry-run       # смета, без генерации
    .venv/bin/python tools/veo_ads.py --tier lite     # сгенерировать все
    .venv/bin/python tools/veo_ads.py --only hero     # один ролик

Без ключа скрипт не падает, а объясняет, что делать — как ai.py/notify.py.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

MODEL = "veo-3.1-generate-preview"
OUT_DIR = Path("ads")

# Цена за секунду, 720p (ai.google.dev/gemini-api/docs/pricing, проверено 2026-08).
# Бесплатного тарифа у Veo нет — нужен проект с включённой оплатой.
TIER_USD_PER_SEC = {"standard": 0.40, "fast": 0.10, "lite": 0.05}


@dataclass(frozen=True)
class Clip:
    name: str
    seconds: int
    prompt: str
    note: str


# Сценарий: три коротких ролика вместо одного длинного. Так их можно ставить в
# сторис по отдельности, а склейка даёт полноценный ад. Промпты описывают
# конкретную Астану, а не «уютную кофейню» вообще — иначе Veo выдаёт сток.
CLIPS: tuple[Clip, ...] = (
    Clip(
        name="hero",
        seconds=8,
        prompt=(
            "Cinematic close-up, evening golden hour inside a small Kazakh bakery in "
            "Astana. Warm amber light from the window. Hands of a young baker in a "
            "flour-dusted apron gently placing unsold croissants, buns and a slice of "
            "cake into a plain kraft paper box. Steam still rising faintly. Shallow "
            "depth of field, 35mm look, soft film grain, slow push-in. No text, no "
            "logos, no on-screen writing. Realistic documentary style, not "
            "advertising-glossy."
        ),
        note="Главный кадр: еда живая, руки настоящие, не сток.",
    ),
    Clip(
        name="pickup",
        seconds=8,
        prompt=(
            "Evening street in Astana, blue hour, city lights beginning to glow. A "
            "young woman in a warm coat walks up to a lit bakery window, smiling, and "
            "shows her phone screen to the cashier across the counter. The cashier "
            "nods and hands her a kraft paper box over the counter. Handheld camera, "
            "natural light, cinematic, shallow depth of field. No text, no logos, no "
            "on-screen writing."
        ),
        note="Показывает механику: пришёл, показал код, забрал.",
    ),
    Clip(
        name="waste",
        seconds=6,
        prompt=(
            "Slow cinematic shot inside a bakery after closing. A tray of unsold "
            "pastries sits under dimmed light. A hand reaches toward a bin, hesitates, "
            "then pulls the tray back. Moody low-key lighting, warm highlights, "
            "shallow depth of field, subtle film grain. Melancholic then hopeful tone. "
            "No text, no logos, no on-screen writing."
        ),
        note="Эмоция проблемы: еду почти выбросили. Ставить первым в склейке.",
    ),
)


def estimate(clips: tuple[Clip, ...], tier: str) -> tuple[int, float]:
    secs = sum(c.seconds for c in clips)
    return secs, secs * TIER_USD_PER_SEC[tier]


def die(msg: str) -> None:
    print(f"\n  ✗ {msg}\n", file=sys.stderr)
    sys.exit(1)


def generate(clip: Clip, tier: str, client) -> Path:
    """Один ролик. Veo — длинная операция: отдаёт handle, готовность опрашиваем."""
    OUT_DIR.mkdir(exist_ok=True)
    dest = OUT_DIR / f"{clip.name}.mp4"
    if dest.exists():
        print(f"  · {clip.name}: уже есть, пропускаю ({dest})")
        return dest

    model = MODEL if tier == "standard" else f"{MODEL}-{tier}"
    print(f"  · {clip.name}: отправляю запрос ({clip.seconds}с, {tier})…")
    op = client.models.generate_videos(model=model, prompt=clip.prompt)

    waited = 0
    while not op.done:
        time.sleep(10)
        waited += 10
        print(f"    ждём… {waited}с")
        op = client.operations.get(op)
        if waited > 900:                       # 15 минут — дальше что-то не так
            die(f"{clip.name}: генерация не завершилась за 15 минут")

    video = op.response.generated_videos[0].video
    client.files.download(file=video)
    video.save(str(dest))
    print(f"    ✓ сохранено: {dest}")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description="Рекламные ролики Yummy через Veo")
    ap.add_argument("--tier", choices=sorted(TIER_USD_PER_SEC), default="fast",
                    help="качество/цена (по умолчанию fast — разумный компромисс)")
    ap.add_argument("--only", help="сгенерировать только один ролик по имени")
    ap.add_argument("--dry-run", action="store_true", help="смета без генерации")
    ap.add_argument("--list", action="store_true", help="показать сценарий")
    args = ap.parse_args()

    clips = CLIPS
    if args.only:
        clips = tuple(c for c in CLIPS if c.name == args.only)
        if not clips:
            die(f"нет ролика «{args.only}». Есть: {', '.join(c.name for c in CLIPS)}")

    if args.list:
        for c in CLIPS:
            print(f"\n[{c.name}] {c.seconds}с — {c.note}\n{c.prompt}")
        return

    secs, usd = estimate(clips, args.tier)
    print(f"\nРоликов: {len(clips)} · всего {secs}с · тариф {args.tier}")
    print(f"Ориентировочно: ${usd:.2f} (~{usd * 540:.0f} ₸ по курсу 540)")
    for t in sorted(TIER_USD_PER_SEC, key=lambda k: TIER_USD_PER_SEC[k]):
        if t != args.tier:
            print(f"  для сравнения --tier {t}: ${secs * TIER_USD_PER_SEC[t]:.2f}")

    if args.dry_run:
        print("\n--dry-run: ничего не сгенерировано, денег не списано.")
        return

    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        die("Нет GEMINI_API_KEY.\n"
            "    1) Ключ: https://aistudio.google.com/apikey\n"
            "    2) У Veo НЕТ бесплатного тарифа — в проекте нужна включённая оплата\n"
            "    3) export GEMINI_API_KEY=ваш_ключ  и запустите снова")

    try:
        from google import genai
    except ImportError:
        die("Нет SDK. Поставьте: uv pip install --python .venv/bin/python google-genai")

    client = genai.Client(api_key=key)
    print()
    for c in clips:
        generate(c, args.tier, client)
    print(f"\nГотово. Файлы в {OUT_DIR.resolve()}\n"
          f"Склейка: ffmpeg -f concat -safe 0 -i list.txt -c copy ads/yummy.mp4")


if __name__ == "__main__":
    main()
