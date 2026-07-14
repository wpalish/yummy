"""Yummy — MVP сервиса surprise-боксов (anti-food-waste), Астана.

При импорте пакета подхватываем локальный `.env` (stdlib, без python-dotenv):
секреты (TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY) лежат в гит-игнорируемом файле
и не должны требовать ручного export при каждом запуске. Уже выставленные
переменные окружения имеют приоритет (setdefault).
"""
import os as _os
import pathlib as _pathlib

__version__ = "0.1.0"


def _load_env() -> None:
    p = _pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        _os.environ.setdefault(key.strip(), value.strip())


_load_env()
