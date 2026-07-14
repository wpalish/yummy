"""Генератор персонализированных сообщений для обхода кофеен (дополняет SALES.md).

Использование:
    python tools/generate_pitch.py --search "Zebra Coffee"        # первое совпадение
    python tools/generate_pitch.py --search "Мангилик Ел, 56"     # по адресу
    python tools/generate_pitch.py --search "Zebra" --save        # записать в колонку «Заметка»

Без ANTHROPIC_API_KEY — детерминированный шаблон на основе скрипта из SALES.md
(не выключается без ключа, как и остальные AI-фичи проекта). С ключом — Claude
пишет более естественное, разное на каждый вызов сообщение под конкретную точку.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEADS_CSV = ROOT / "data" / "leads" / "astana_coffee_leads.csv"

sys.path.insert(0, str(ROOT))
from app import ai as ai_mod  # noqa: E402


def _load_leads() -> list[dict]:
    if not LEADS_CSV.exists():
        print(f"Не найден {LEADS_CSV} — сначала собери лид-базу (см. SALES.md).", file=sys.stderr)
        return []
    with LEADS_CSV.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _find(leads: list[dict], query: str) -> list[dict]:
    q = query.lower()
    return [r for r in leads if q in r["Сеть"].lower() or q in r["Адрес"].lower()]


def _fallback_pitch(lead: dict) -> str:
    """Детерминированный шаблон по скрипту из SALES.md — без AI, но персонализирован."""
    name, addr = lead["Сеть"], lead["Адрес"]
    return (
        f"Здравствуйте! Я Алишер, делаю сервис Yummy — помогаем кофейням Астаны "
        f"продавать вечерние излишки вместо списания. Заметил вашу точку «{name}» "
        f"на {addr} — у вас к закрытию остаётся выпечка?\n\n"
        f"Механика простая: вечером выставляете сюрприз-бокс из остатков, "
        f"например 5 боксов по 990 ₸. Люди бронируют онлайн, приходят с QR, "
        f"сотрудник выдаёт. Цену и количество ставите сами. На пилоте — 0 ₸ "
        f"комиссии. Спишете 3-5 тыс ₸ — а тут живая выручка.\n\n"
        f"Могу подключить за 10 минут, первый бокс — хоть завтра вечером. "
        f"Какой у вас WhatsApp?"
    )


async def _ai_pitch(lead: dict) -> str:
    name, addr, rating = lead["Сеть"], lead["Адрес"], lead.get("Рейтинг", "")
    return await ai_mod.complete(
        system=(
            "Ты — Алишер, основатель Yummy (Астана): сервис, помогающий кофейням "
            "продавать вечерние излишки едой сюрприз-боксами вместо списания, "
            "вместо WhatsApp/Instagram-постов у самой кофейни. Пиши личное, тёплое, "
            "не шаблонное сообщение для первого контакта с конкретной кофейней "
            "(WhatsApp/Telegram). Обязательно: упомяни название и адрес точки, "
            "предложи выставить сюрприз-бокс вечером, подчеркни 0 ₸ комиссии на "
            "пилоте, закончи вопросом про WhatsApp. Без markdown, без emoji, "
            "5-8 предложений, на русском."
        ),
        user=f"Кофейня: {name}. Адрес: {addr}. Рейтинг в 2GIS: {rating or 'нет данных'}.",
        max_tokens=350,
        temperature=0.9,
    )


def _save_note(query: str, lead: dict, pitch: str) -> None:
    leads = _load_leads()
    for r in leads:
        if r["Сеть"] == lead["Сеть"] and r["Адрес"] == lead["Адрес"]:
            r["Заметка"] = pitch.replace("\n", " ").strip()[:200]
    with LEADS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=leads[0].keys())
        w.writeheader()
        w.writerows(leads)
    print(f"→ записано в «Заметка» для {lead['Сеть']} ({lead['Адрес']})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--search", required=True, help="часть названия сети или адреса")
    ap.add_argument("--save", action="store_true", help="записать сообщение в колонку «Заметка»")
    ap.add_argument("--all", action="store_true", help="сгенерировать для всех совпадений, не только первого")
    args = ap.parse_args()

    leads = _load_leads()
    if not leads:
        return 1
    matches = _find(leads, args.search)
    if not matches:
        print(f"Ничего не найдено по «{args.search}»", file=sys.stderr)
        return 1

    targets = matches if args.all else matches[:1]
    print(f"Найдено {len(matches)} · генерирую для {len(targets)} "
          f"({'AI' if ai_mod.is_configured() else 'шаблон, ANTHROPIC_API_KEY не задан'})\n")

    for lead in targets:
        try:
            pitch = asyncio.run(_ai_pitch(lead)) if ai_mod.is_configured() else _fallback_pitch(lead)
        except ai_mod.AIUnavailable:
            pitch = _fallback_pitch(lead)
        print(f"=== {lead['Сеть']} · {lead['Адрес']} ===")
        print(pitch)
        print()
        if args.save:
            _save_note(args.search, lead, pitch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
