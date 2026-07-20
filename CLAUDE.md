# Yummy — карта проекта для Claude Code

Anti-food-waste маркетплейс surprise-боксов для Астаны (аналог Too Good To Go).
Кофейни продают вечерние излишки боксами со скидкой 40–70%, юзеры бронируют и
забирают самовывозом по QR/коду.

**Живое:** сайт https://wpalish.github.io/yummy · бэкенд
https://yummy-astana.onrender.com · репо github.com/wpalish/yummy
**Telegram-бот:** @yummy_astana_bot (уведомления о новых боксах)

## Стек (ВАЖНО — НЕ Node/bun/Next)

- **Backend:** Python 3.12 + FastAPI + SQLite (WAL, индексы). Без ORM — сырой
  `sqlite3` с плейсхолдерами.
- **Frontend:** vanilla JS, один файл `app/static/index.html` (~1800 строк).
  Без React/сборщиков.
- **Тесты:** pytest (81 тест). Запуск: `.venv/bin/python -m pytest -q`.
- **Пакеты:** venv в `.venv/` без pip — ставить через `uv pip install --python .venv/bin/python <pkg>`.
- **Задачи:** `make test` / `make docs` / `make dev` (порт 8021).

## Карта файлов

| Путь | Что |
|------|-----|
| `app/main.py` | FastAPI-эндпоинты, security-заголовки, rate-limit |
| `app/db.py` | `Store` — потокобезопасная обёртка над SQLite |
| `app/models.py` | Pydantic-модели (пароль-хеш/токены НИКОГДА не в ответе) |
| `app/accounts.py` | JWT-аутентификация (access+refresh, PBKDF2), RBAC |
| `app/ai.py` | Claude API через httpx (описания боксов, модерация) — фолбэк без ключа |
| `app/notify.py` | Telegram-рассылка новых боксов (getUpdates-поллинг) |
| `app/seed.py` | демо-данные (6 партнёров, 7 боксов) |
| `app/static/src/shell.html` | HTML+CSS-каркас + плейсхолдер `@@JS_BUNDLE@@` |
| `app/static/src/js/*.js` | JS-модули фронта (склеиваются в порядке имён) |
| `app/static/index.html` | ГЕНЕРИРУЕМЫЙ (`make index`) — не править руками |
| `tools/build_index.py` | сборка index.html из src/ (все модули в 1 `<script>`) |
| `docs/index.html` | сборка для GitHub Pages (client-store демо ИЛИ живой бэкенд) |
| `tools/build_docs.py` | `make docs` → генерит docs/ из app/static |
| `data/leads/` | 162 реальных лида кофеен Астаны (для продаж, НЕ публикуются) |

## Критичные инварианты

1. **index.html И docs/index.html — генерируемые.** Фронт правится в
   `app/static/src/` (shell.html + js/*.js), потом `make index`. Для Pages —
   `YUMMY_PAGES_API_BASE=https://yummy-astana.onrender.com make docs` (сам
   пересоберёт index). Все js-модули склеиваются в ОДИН inline `<script>` —
   top-level const/let общие между «модулями», порядок = имена файлов.
   test_index_build стережёт, что коммит index.html совпадает со сборкой.
2. **Владение по коду заказа** (redeem/cancel/refund) — как в /redeem, а не по ID из тела.
3. **Отзыв только по issued-заказу** через `user_orders()`, не по сырому ID.
4. **AI/Telegram деградируют без ключа** — фича не ломается, отдаёт фолбэк.
5. **Секреты — в `.env`** (gitignore). В репо токенов нет.
6. **Render:** автодеплоя НЕТ (репо подключён по public URL) — после пуша нужен
   Manual Deploy на дашборде.

## Локаль

KZ через `const KZ={}` (словарь) + `const KZ_RX=[]` (regex) + MutationObserver.
Юр.документы намеренно на русском.

## Что НЕ делать

- Не тащить тяжёлые зависимости (проект намеренно на stdlib-подходе).
- Не заявлять фичи, которых нет (пользователь на этом настаивает — «пилот/демо»
  честнее ложного «прод»).
- Не переписывать фронт на фреймворк ради одной формы.
