"""Telegram-уведомления о новых боксах (бот @yummy_astana_bot).

Подписка: человек пишет боту /start — при следующей рассылке (или ручном
`python -m app.notify`) getUpdates подберёт его chat_id в tg_subscribers.
Вебхук не нужен: поллим getUpdates перед каждой рассылкой — на пилотном
масштабе этого достаточно и работает даже с localhost (в отличие от вебхука,
которому нужен публичный HTTPS-адрес).

Без TELEGRAM_BOT_TOKEN модуль выключен: рассылка молча пропускается, бокс
публикуется как обычно — фича деградирует, а не ломает основной флоу.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger("yummy.notify")

_TIMEOUT = 5.0
_TZ = ZoneInfo("Asia/Almaty")  # окна выдачи храним в UTC, людям пишем в местном


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _public_url() -> str:
    return os.getenv("YUMMY_PUBLIC_URL", "https://wpalish.github.io/yummy/").rstrip("/") + "/"


def _channel() -> str:
    """Публичный канал-витрина: @username или числовой -100… id. Пусто → выкл."""
    return os.getenv("YUMMY_TG_CHANNEL", "").strip()


def is_configured() -> bool:
    return bool(_token())


def _api(method: str, **params) -> dict | list:
    r = httpx.post(f"https://api.telegram.org/bot{_token()}/{method}",
                   json=params, timeout=_TIMEOUT)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram {method}: {data.get('description', r.status_code)}")
    return data["result"]


def extract_subscribers(updates: list[dict]) -> list[tuple[int, str]]:
    """Достать (chat_id, имя) из личных сообщений боту; группы/каналы игнорируем."""
    out: list[tuple[int, str]] = []
    for u in updates:
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private" and chat.get("id"):
            name = (" ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
                    or chat.get("username") or "")
            out.append((int(chat["id"]), name))
    return out


def pull_subscribers(store) -> int:
    """Подобрать новых подписчиков из getUpdates. Возвращает число новых."""
    if not is_configured():
        return 0
    offset = int(store.meta_get("tg_offset", "0"))
    updates = _api("getUpdates", offset=offset + 1, timeout=0)
    if not updates:
        return 0
    store.meta_set("tg_offset", str(max(u["update_id"] for u in updates)))
    new = 0
    for chat_id, name in extract_subscribers(updates):
        if store.tg_add_subscriber(chat_id, name):
            new += 1
            try:
                _api("sendMessage", chat_id=chat_id, text=(
                    "Привет! 🥐 Ты подписан на боксы Yummy — напишу, как только "
                    "кофейни выставят свежие вечерние боксы со скидкой."))
            except Exception:  # приветствие не критично для подписки
                log.warning("notify: welcome to %s failed", chat_id)
    return new


def _hhmm(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(_TZ).strftime("%H:%M")


def box_message(box) -> str:
    discount = round((1 - box.price / box.value_est) * 100) if box.value_est else 0
    return (f"🥐 {box.partner_name}: новый бокс «{box.title}»\n"
            f"{box.price} ₸ вместо {box.value_est} ₸ (−{discount}%) · осталось {box.qty_left}\n"
            f"Забрать сегодня {_hhmm(box.pickup_from)}–{_hhmm(box.pickup_to)} · {box.address}\n"
            f"{_public_url()}?box={box.id}")


def _box_button(box) -> dict:
    """Inline-кнопка «Забрать бокс» → карточка на сайте."""
    return {"inline_keyboard": [[{"text": "🥐 Забрать бокс", "url": f"{_public_url()}?box={box.id}"}]]}


def post_to_channel(box) -> bool:
    """Опубликовать бокс в канал-витрину. Best-effort: сбой не роняет публикацию.
    Бот должен быть админом канала с правом постинга. Пусто/сбой → False."""
    ch = _channel()
    if not is_configured() or not ch:
        return False
    try:
        _api("sendMessage", chat_id=ch, text=box_message(box),
             reply_markup=_box_button(box), disable_web_page_preview=False)
        return True
    except Exception as e:
        log.warning("notify: channel post failed: %s", e)
        return False


def broadcast_new_box(store, box) -> int:
    """Разослать бокс: в канал-витрину (если задан) + личным подписчикам.
    Best-effort: сбои не роняют публикацию бокса."""
    if not is_configured():
        return 0
    post_to_channel(box)  # публичная витрина — двигатель охвата
    # В webhook-режиме подписчики ловятся эндпоинтом /telegram/webhook, а
    # getUpdates при активном webhook возвращает 409 — поэтому pull только
    # в polling-режиме (нет TELEGRAM_WEBHOOK_SECRET).
    if not os.getenv("TELEGRAM_WEBHOOK_SECRET"):
        try:
            pull_subscribers(store)
        except Exception as e:
            log.warning("notify: pull failed: %s", e)
    sent = 0
    for chat_id in store.tg_subscribers():
        try:
            _api("sendMessage", chat_id=chat_id, text=box_message(box),
                 reply_markup=_box_button(box))
            sent += 1
        except Exception as e:
            msg = str(e).lower()
            if "blocked" in msg or "chat not found" in msg or "deactivated" in msg:
                store.tg_remove_subscriber(chat_id)  # заблокировал бота — не долбим
            else:
                log.warning("notify: send to %s failed: %s", chat_id, e)
    log.info("notify: box %s → %d подписчикам", box.id, sent)
    return sent


if __name__ == "__main__":  # утилиты: python -m app.notify [channel-test]
    import sys

    from .db import Store

    s = Store()
    if len(sys.argv) > 1 and sys.argv[1] == "channel-test":
        # проверка связи с каналом: постим первый доступный бокс (или заглушку)
        if not _channel():
            print("YUMMY_TG_CHANNEL не задан — канал выключен")
            raise SystemExit(1)
        boxes = s.boxes_available()
        box = boxes[0] if boxes else None
        if not box:
            print("нет боксов для теста — создайте бокс и повторите")
            raise SystemExit(1)
        ok = post_to_channel(box)
        print(f"пост в канал {_channel()}: {'ok' if ok else 'НЕ УДАЛОСЬ (бот админ канала?)'}")
        raise SystemExit(0 if ok else 1)
    n = pull_subscribers(s)
    print(f"новых подписчиков: {n}, всего: {len(s.tg_subscribers())}")


def notify_new_order(order) -> bool:
    """Сообщение о новой брони в операционный чат (партнёр/админ смотрят его).
    YUMMY_ORDERS_CHAT_ID пуст → фича выключена, флоу заказа не страдает."""
    chat = os.getenv("YUMMY_ORDERS_CHAT_ID", "").strip()
    if not (chat and _token()):
        return False
    try:
        _api("sendMessage", chat_id=chat, text=(
            f"🧺 Новая бронь {order.code}\n"
            f"{order.partner_name} · {order.category_ru} · {order.price} ₸\n"
            f"Выдача {_hhmm(order.pickup_from)}–{_hhmm(order.pickup_to)}"))
        return True
    except Exception as exc:                    # noqa: BLE001 — не ломаем заказ
        log.warning("notify_new_order: %s", exc)
        return False
