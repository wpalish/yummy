"""AI-клиент: без ключа — явная деградация (не тихий сбой).

Проект не тянет pytest-asyncio — async-функции гоняются через asyncio.run()
в обычных sync-тестах. Реальных сетевых вызовов к Anthropic нет: без ключа
complete() бросает AIUnavailable раньше, чем дойдёт до httpx.
"""
from __future__ import annotations

import asyncio

import pytest

from app import ai as ai_mod


@pytest.fixture(autouse=True)
def _reset_key(monkeypatch):
    """Каждый тест сам решает, задан ли ключ — не наследуем окружение разработчика."""
    monkeypatch.setattr(ai_mod, "_API_KEY", "")


def test_not_configured_by_default():
    assert ai_mod.is_configured() is False


def test_complete_raises_without_key():
    with pytest.raises(ai_mod.AIUnavailable):
        asyncio.run(ai_mod.complete("sys", "user"))


def test_generate_box_description_rejects_empty_notes():
    with pytest.raises(ValueError):
        asyncio.run(ai_mod.generate_box_description("Сладкий бокс", "   "))


def test_fallback_box_description_deterministic():
    d1 = ai_mod.fallback_box_description("Сладкий бокс", "2 круассана, маффин")
    d2 = ai_mod.fallback_box_description("Сладкий бокс", "2 круассана, маффин")
    assert d1 == d2
    assert "круассана" in d1 and len(d1) < 200


# ---- эвристическая модерация (работает без ключа) -------------------------- #
def test_heuristic_allows_normal_text():
    ok, _ = ai_mod.heuristic_moderate("Очень вкусный бокс, взяла с подругой, всё понравилось!")
    assert ok is True


def test_heuristic_blocks_too_short():
    ok, reason = ai_mod.heuristic_moderate("ок")
    assert not ok and "коротк" in reason


def test_heuristic_blocks_profanity():
    ok, reason = ai_mod.heuristic_moderate("это полная хуйня, не берите")
    assert not ok and "лекс" in reason


def test_heuristic_blocks_spam_link():
    ok, reason = ai_mod.heuristic_moderate("отличный бокс, пишите в телеграм t.me/spam123")
    assert not ok


def test_heuristic_blocks_caps():
    ok, reason = ai_mod.heuristic_moderate("ЭТО ПРОСТО УЖАСНО ВСЕ ПЛОХО ОЧЕНЬ")
    assert not ok and "капс" in reason


def test_heuristic_blocks_char_spam():
    ok, _ = ai_mod.heuristic_moderate("вкусноооооооооо!")
    assert not ok


def test_moderate_review_falls_back_to_heuristic_without_key():
    ok, reason = asyncio.run(ai_mod.moderate_review("Нормальный отзыв, бокс понравился."))
    assert ok is True and reason == ""

    ok2, reason2 = asyncio.run(ai_mod.moderate_review("сука дно полное"))
    assert ok2 is False and reason2
