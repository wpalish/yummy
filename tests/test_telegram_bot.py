"""Тесты интерактивного Telegram-бота — без сети, notify._api замокан."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import notify, telegram_bot
from app.db import Store
from app.models import BoxCreate, Partner


@pytest.fixture
def st(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TEST")
    s = Store(path=tmp_path / "t.db")
    s.upsert_partner(Partner(id="p1", name="Coffee Point", district="Есильский р-н",
                             address="пр. Мангилик Ел, 55"))
    return s


@pytest.fixture
def sent(monkeypatch):
    """Перехват исходящих sendMessage."""
    calls = []
    monkeypatch.setattr(notify, "_api",
                        lambda method, **p: calls.append((method, p)) or {})
    return calls


def _msg(chat_id, text, first_name="Али"):
    return {"message": {"chat": {"id": chat_id, "type": "private",
                                 "first_name": first_name}, "text": text}}


def _box(st, bid="b1"):
    now = datetime.now(timezone.utc)
    return st.create_box(bid, BoxCreate(
        partner_id="p1", category="sweet", title="Sweet Box", price=990, value_est=2600,
        qty=5, pickup_from=(now - timedelta(minutes=5)).isoformat(),
        pickup_to=(now + timedelta(hours=3)).isoformat(),
    ))


def test_start_subscribes_and_welcomes(st, sent):
    telegram_bot.handle_update(st, _msg(42, "/start"))
    assert st.tg_subscribers() == [42]
    assert sent and sent[0][0] == "sendMessage" and sent[0][1]["chat_id"] == 42
    assert "Yummy" in sent[0][1]["text"]


def test_start_idempotent(st, sent):
    telegram_bot.handle_update(st, _msg(42, "/start"))
    telegram_bot.handle_update(st, _msg(42, "/start"))
    assert st.tg_subscribers() == [42]  # дубля нет


def test_stop_unsubscribes(st, sent):
    st.tg_add_subscriber(42, "Али")
    telegram_bot.handle_update(st, _msg(42, "/stop"))
    assert st.tg_subscribers() == []
    assert "отписал" in sent[-1][1]["text"].lower()


def test_boxes_lists_available(st, sent):
    _box(st)
    telegram_bot.handle_update(st, _msg(42, "/boxes"))
    text = sent[-1][1]["text"]
    assert "Coffee Point" in text and "990" in text and "Sweet Box" in text


def test_boxes_empty(st, sent):
    telegram_bot.handle_update(st, _msg(42, "/boxes"))
    assert "доступных боксов нет" in sent[-1][1]["text"]


def test_help(st, sent):
    telegram_bot.handle_update(st, _msg(42, "/help"))
    assert "/boxes" in sent[-1][1]["text"]


def test_unknown_command_hint(st, sent):
    telegram_bot.handle_update(st, _msg(42, "приветик"))
    assert "/help" in sent[-1][1]["text"]


def test_group_messages_ignored(st, sent):
    telegram_bot.handle_update(st, {"message": {"chat": {"id": -100, "type": "group"},
                                                "text": "/start"}})
    assert st.tg_subscribers() == [] and sent == []


def test_command_with_botname_suffix(st, sent):
    telegram_bot.handle_update(st, _msg(42, "/boxes@yummy_astana_bot"))
    assert sent and "боксов" in sent[-1][1]["text"].lower()


def test_webhook_enabled_needs_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    assert telegram_bot.webhook_enabled() is False
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TEST")
    assert telegram_bot.webhook_enabled() is True  # секрет выводится из токена


def test_secret_derived_from_token_deterministic(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TEST")
    s1 = telegram_bot._secret()
    assert len(s1) == 32 and s1 == telegram_bot._secret()  # стабилен
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "explicit-wins")
    assert telegram_bot._secret() == "explicit-wins"  # явный имеет приоритет
