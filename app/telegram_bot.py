"""Интерактивный Telegram-бот @yummy_astana_bot — webhook + команды.

Дополняет app/notify.py (рассылка новых боксов): теперь бот РЕАЛЬНО отвечает на
команды. Работает через webhook (публичный HTTPS появился после деплоя на
Render), а не long-polling — free-инстанс Render не держит постоянный процесс,
а Telegram сам ретраит доставку при холодном старте.

Команды:
  /start  — подписаться, приветствие + как работает
  /boxes  — показать боксы, доступные сейчас
  /stop   — отписаться
  /help   — список команд

Безопасность: Telegram шлёт заголовок X-Telegram-Bot-Api-Secret-Token, равный
TELEGRAM_WEBHOOK_SECRET. Проверяем его — иначе кто угодно мог бы слать боту
фейковые апдейты. Без секрета webhook-эндпоинт отключён (503).

Активация (после деплоя):
  TELEGRAM_WEBHOOK_SECRET=<секрет> на бэкенде (Render env), затем
  YUMMY_PUBLIC_API=https://yummy-astana.onrender.com python -m app.telegram_bot set-webhook
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Header, HTTPException
from fastapi import Request as HttpRequest

from . import notify
from .db import Store

log = logging.getLogger("yummy.tgbot")
router = APIRouter(tags=["Telegram"])

store = Store()

_WELCOME = (
    "Привет! 🥐 Это Yummy — спасаем свежую еду из кофеен Астаны со скидкой до 70%.\n\n"
    "Ты подписан: напишу, как только кофейни выставят вечерние боксы.\n\n"
    "Команды:\n"
    "/boxes — что доступно прямо сейчас\n"
    "/stop — отписаться\n"
    "/help — помощь"
)
_HELP = (
    "Команды бота Yummy:\n"
    "/boxes — боксы, доступные сейчас\n"
    "/start — подписаться на новые боксы\n"
    "/stop — отписаться\n\n"
    f"Сайт: {notify._public_url()}"
)


def _secret() -> str:
    return os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


def webhook_enabled() -> bool:
    return bool(notify.is_configured() and _secret())


def _send(chat_id: int, text: str) -> None:
    try:
        notify._api("sendMessage", chat_id=chat_id, text=text,
                    disable_web_page_preview=True)
    except Exception as e:  # ответ не критичен — не роняем webhook
        log.warning("tgbot: send to %s failed: %s", chat_id, e)


def _boxes_text(st: Store, limit: int = 8) -> str:
    boxes = st.boxes_available(None)[:limit]
    if not boxes:
        return "Сейчас доступных боксов нет 😔 Напишу, как только появятся."
    lines = ["🛍 Доступно сейчас:\n"]
    for b in boxes:
        disc = round((1 - b.price / b.value_est) * 100) if b.value_est else 0
        lines.append(
            f"• {b.partner_name} — «{b.title}» {b.price} ₸ (−{disc}%), "
            f"осталось {b.qty_left}, до {notify._hhmm(b.pickup_to)}"
        )
    lines.append(f"\nЗабронировать: {notify._public_url()}")
    return "\n".join(lines)


def handle_update(st: Store, update: dict) -> None:
    """Обработать один Telegram-апдейт. Только личные сообщения-команды."""
    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") != "private" or not chat.get("id"):
        return
    chat_id = int(chat["id"])
    text = (msg.get("text") or "").strip()
    cmd = text.split()[0].split("@")[0].lower() if text else ""

    if cmd == "/start":
        name = (" ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
                or chat.get("username") or "")
        st.tg_add_subscriber(chat_id, name)  # идемпотентно
        _send(chat_id, _WELCOME)
    elif cmd == "/stop":
        st.tg_remove_subscriber(chat_id)
        _send(chat_id, "Готово — отписал. Вернуться: /start 👋")
    elif cmd == "/boxes":
        _send(chat_id, _boxes_text(st))
    elif cmd == "/help":
        _send(chat_id, _HELP)
    elif text:
        _send(chat_id, "Не знаю такой команды. Попробуй /boxes или /help 🙂")


@router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(
    request: HttpRequest,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> dict:
    """Приём апдейтов от Telegram. Всегда 200 (кроме плохого секрета) — иначе
    Telegram будет ретраить."""
    if not webhook_enabled():
        raise HTTPException(503, "Telegram webhook не настроен")
    if x_telegram_bot_api_secret_token != _secret():
        raise HTTPException(403, "bad secret")
    try:
        update = await request.json()
        handle_update(store, update)
    except Exception as e:  # не даём Telegram ретраить из-за нашей ошибки
        log.warning("tgbot: update failed: %s", e)
    return {"ok": True}


# --------------------------------------------------------------------------- #
#  CLI регистрации webhook: python -m app.telegram_bot set-webhook|delete|info
# --------------------------------------------------------------------------- #
def _api_base() -> str:
    return os.getenv("YUMMY_PUBLIC_API", "https://yummy-astana.onrender.com").rstrip("/")


def set_webhook() -> dict:
    if not webhook_enabled():
        raise SystemExit("Нужны TELEGRAM_BOT_TOKEN и TELEGRAM_WEBHOOK_SECRET")
    url = f"{_api_base()}/telegram/webhook"
    return notify._api(
        "setWebhook", url=url, secret_token=_secret(),
        allowed_updates=["message"], drop_pending_updates=True,
    )  # type: ignore[return-value]


def main() -> int:
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "info"
    if action == "set-webhook":
        print("setWebhook →", _api_base() + "/telegram/webhook")
        print(set_webhook())
    elif action == "delete-webhook":
        print(notify._api("deleteWebhook", drop_pending_updates=False))
    else:
        print(notify._api("getWebhookInfo"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
