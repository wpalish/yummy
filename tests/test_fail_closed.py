"""Fail-closed: авторизация ВКЛЮЧЕНА по умолчанию.

Регресс-защита от худшей архитектурной дыры: раньше _ENFORCE был fail-open —
забытый YUMMY_ENFORCE_AUTH на новом окружении открывал админку миру.
"""
from __future__ import annotations

import pytest

from app.accounts import _enforce_from_env, assert_prod_config


def test_enforce_on_by_default(monkeypatch):
    monkeypatch.delenv("YUMMY_ENFORCE_AUTH", raising=False)
    assert _enforce_from_env() is True          # нет флага → защита ВКЛЮЧЕНА


@pytest.mark.parametrize("v", ["0", "false", "no", "False", "NO"])
def test_explicit_optout(monkeypatch, v):
    monkeypatch.setenv("YUMMY_ENFORCE_AUTH", v)
    assert _enforce_from_env() is False         # открыть можно только явно


@pytest.mark.parametrize("v", ["1", "true", "yes", "", "anything"])
def test_everything_else_enforces(monkeypatch, v):
    """Мусорное значение флага = защита включена, а не выключена."""
    monkeypatch.setenv("YUMMY_ENFORCE_AUTH", v)
    assert _enforce_from_env() is True


def test_default_secret_with_enforce_fails_fast(monkeypatch):
    """Включённый auth + dev-секрет = подделываемые токены → падаем на старте."""
    monkeypatch.delenv("YUMMY_ENFORCE_AUTH", raising=False)
    monkeypatch.delenv("YUMMY_SECRET_KEY", raising=False)
    import app.accounts as am
    monkeypatch.setattr(am, "_SECRET", am._DEFAULT_SECRET)
    with pytest.raises(RuntimeError):
        assert_prod_config()


def test_optout_with_default_secret_ok(monkeypatch):
    monkeypatch.setenv("YUMMY_ENFORCE_AUTH", "0")
    assert_prod_config()                        # локальное демо — законно
