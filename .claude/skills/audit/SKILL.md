---
name: audit
description: Полный аудит Yummy — безопасность, тесты, сложность, зависимости. Пишет AUDIT_REPORT.md.
allowed-tools: Read, Grep, Glob, Bash
---

# Полный аудит проекта Yummy

Комплексная инспекция. Стек — Python/FastAPI/SQLite, НЕ Node.

## 1. Безопасность
- `grep -rEn "(sk-ant|token|password|secret)\s*=\s*[\"']" app tools` — захардкоженные секреты.
- Проверить, что `.env` в `.gitignore` и не в staged.
- API-эндпоинты: у write/AI есть rate-limit? Владение через `WHERE user_id=?`/код, не по ID из тела?
- SQL: везде плейсхолдеры, нет конкатенации (`grep -n "execute(" app/db.py`).
- Ответы не отдают pw_hash/токены (проверить `response_model`).
- Если установлен bandit: `bandit -r app tools -q`.

## 2. Тесты
- `rm -f spasibox.db* && .venv/bin/python -m pytest -q` — все зелёные.
- Перечислить непокрытые критичные пути (auth, выдача, оплата-заглушка, возврат).

## 3. Сложность
- Функции >50 строк, файлы >800 строк (кроме `index.html`).
- God-функции, глубокая вложенность >4.

## 4. Зависимости
- `requirements.txt` — версии запинены? Неиспользуемое?
- Проверить, что фичи деградируют без ключей (ai.py, notify.py).

## 5. Инфраструктура
- Dockerfile: non-root? Render env актуальны (DEPLOY.md)?
- docs/index.html пересобираем из app/static (не расходится)?

Вывести отчёт в `AUDIT_REPORT.md` с severity: 🔴 Critical | 🟠 High | 🟡 Medium | 🟢 Low.
