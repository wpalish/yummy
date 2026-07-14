"""Тесты Telegram-уведомлений о новых боксах — без сети, _api мокается."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import notify
from app.db import Store
from app.models import BoxCreate, Partner


@pytest.fixture
def store(tmp_path):
    s = Store(path=tmp_path / "t.db")
    s.upsert_partner(Partner(id="p1", name="Coffee Point", district="Есильский р-н",
                             address="пр. Мангилик Ел, 55"))
    return s


def _box(store):
    now = datetime.now(timezone.utc)
    return store.create_box("b1", BoxCreate(
        partner_id="p1", category="sweet", title="Sweet Box", price=990, value_est=2600,
        qty=5, pickup_from=(now + timedelta(hours=1)).isoformat(),
        pickup_to=(now + timedelta(hours=4)).isoformat(),
    ))


# --------------------------------------------------------------------------- #
#  Подписчики в БД
# --------------------------------------------------------------------------- #
def test_subscribers_crud(store):
    assert store.tg_subscribers() == []
    assert store.tg_add_subscriber(42, "Алишер") is True
    assert store.tg_add_subscriber(42, "Алишер") is False  # дубль не растит список
    assert store.tg_add_subscriber(77) is True
    assert store.tg_subscribers() == [42, 77]
    store.tg_remove_subscriber(42)
    assert store.tg_subscribers() == [77]


def test_meta_roundtrip(store):
    assert store.meta_get("tg_offset", "0") == "0"
    store.meta_set("tg_offset", "123")
    store.meta_set("tg_offset", "456")  # upsert перезаписывает
    assert store.meta_get("tg_offset") == "456"


# --------------------------------------------------------------------------- #
#  Разбор getUpdates
# --------------------------------------------------------------------------- #
def test_extract_subscribers_private_only():
    updates = [
        {"update_id": 1, "message": {"chat": {"id": 100, "type": "private",
                                              "first_name": "Али", "last_name": "Н."}}},
        {"update_id": 2, "message": {"chat": {"id": -500, "type": "group", "title": "чат"}}},
        {"update_id": 3, "edited_message": {"chat": {"id": 200, "type": "private"}}},
        {"update_id": 4, "message": {"chat": {"id": 300, "type": "private",
                                              "username": "nickonly"}}},
    ]
    assert notify.extract_subscribers(updates) == [(100, "Али Н."), (300, "nickonly")]


# --------------------------------------------------------------------------- #
#  Выключено без токена
# --------------------------------------------------------------------------- #
def test_disabled_without_token(store, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    called = []
    monkeypatch.setattr(notify, "_api", lambda *a, **k: called.append(a))
    assert notify.is_configured() is False
    assert notify.pull_subscribers(store) == 0
    assert notify.broadcast_new_box(store, _box(store)) == 0
    assert called == []  # ни одного обращения к Telegram


# --------------------------------------------------------------------------- #
#  pull: новые подписчики + offset + welcome
# --------------------------------------------------------------------------- #
def test_pull_adds_subscribers_and_offset(store, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TEST")
    calls = []

    def fake_api(method, **params):
        calls.append((method, params))
        if method == "getUpdates":
            return [{"update_id": 10, "message": {"chat": {"id": 42, "type": "private",
                                                           "first_name": "Али"}}}]
        return {}

    monkeypatch.setattr(notify, "_api", fake_api)
    assert notify.pull_subscribers(store) == 1
    assert store.tg_subscribers() == [42]
    assert store.meta_get("tg_offset") == "10"
    welcome = [c for c in calls if c[0] == "sendMessage"]
    assert len(welcome) == 1 and welcome[0][1]["chat_id"] == 42
    # повторный pull с тем же ответом — дубль не добавляется, welcome не шлётся
    assert notify.pull_subscribers(store) == 0
    assert store.tg_subscribers() == [42]


# --------------------------------------------------------------------------- #
#  broadcast: рассылка + чистка заблокировавших
# --------------------------------------------------------------------------- #
def test_broadcast_sends_and_prunes_blocked(store, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TEST")
    store.tg_add_subscriber(42, "живой")
    store.tg_add_subscriber(77, "заблокировал")
    box = _box(store)
    sent_to = []

    def fake_api(method, **params):
        if method == "getUpdates":
            return []
        if params.get("chat_id") == 77:
            raise RuntimeError("telegram sendMessage: Forbidden: bot was blocked by the user")
        sent_to.append(params["chat_id"])
        return {}

    monkeypatch.setattr(notify, "_api", fake_api)
    assert notify.broadcast_new_box(store, box) == 1
    assert sent_to == [42]
    assert store.tg_subscribers() == [42]  # 77 вычищен


# --------------------------------------------------------------------------- #
#  Текст сообщения: цена/скидка/ссылка/астанинское время
# --------------------------------------------------------------------------- #
def test_box_message_content(store):
    now = datetime(2026, 7, 14, 6, 0, tzinfo=timezone.utc)  # 06:00 UTC = 11:00 Астаны
    box = store.create_box("b1", BoxCreate(
        partner_id="p1", category="sweet", title="Sweet Box", price=990, value_est=2600,
        qty=5, pickup_from=now.isoformat(),
        pickup_to=(now + timedelta(hours=2)).isoformat(),
    ))
    text = notify.box_message(box)
    assert "Coffee Point" in text and "«Sweet Box»" in text
    assert "990 ₸" in text and "−62%" in text
    assert "11:00–13:00" in text  # UTC переведён в Asia/Almaty
    assert "?box=b1" in text
