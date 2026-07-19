"""Общая изоляция тестов от внешних сервисов.

app/__init__ подхватывает локальный .env (setdefault), где у разработчика
лежат НАСТОЯЩИЕ TELEGRAM_BOT_TOKEN / ANTHROPIC_API_KEY. Тесты не должны
ходить в сеть (TestClient выполняет BackgroundTasks синхронно — публикация
бокса в тесте разослала бы реальные Telegram-сообщения). Выставляем пустые
значения ДО первого импорта app: setdefault их не перезапишет, а
is_configured() честно вернёт False. Тесты, которым нужен ключ, ставят его
сами через monkeypatch.
"""
import os

os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
# Auth теперь fail-closed (включён по умолчанию). Базовые тесты работают в
# открытом режиме; тесты авторизации включают её сами (monkeypatch _ENFORCE=True).
os.environ["YUMMY_ENFORCE_AUTH"] = "0"
