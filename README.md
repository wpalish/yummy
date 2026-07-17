# Yummy — MVP сервиса surprise-боксов (anti-food-waste)

Маркетплейс «спаси еду»: кофейни и пекарни Астаны продают свежие, но не
проданные за день товары **боксами** со скидкой 40–70%, пользователи бронируют,
оплачивают и забирают самовывозом. Бизнес режет списания — люди едят дешевле.

Это **рабочий MVP**, максимально близкий к реальному продукту: полный флоу
**публикация → бронь → оплата → код/QR → выдача** с правилами no-show и возврата.

## Три поверхности (одно приложение)

| Роль | Что умеет |
|------|-----------|
| 🛍 **Магазин** (покупатель) | каталог боксов на ленте, фильтр по району, карточка с «ориентировочной ценностью» и FOMO «осталось N», бронь + демо-оплата, **QR-код и код выдачи**, «Мои заказы» |
| 🧑‍🍳 **Партнёр** (кофейня) | создать бокс за минуту, список своих боксов и броней, **выдача заказа по коду** |
| 🛠 **Админ** | метрики пилота (GMV, fill rate, no-show, возвраты, take-rate), все заказы, возвраты |

## Бизнес-правила (как в реальном продукте)

- **Surprise box** — точный состав может отличаться, это набор остатков дня.
- **No-show** — если не забрал в окне самовывоза, заказ сгорает, предоплата не возвращается.
- **Возврат** — если заведение не выдало, полный refund (бокс возвращается в наличие).
- Бронь атомарно уменьшает остаток; повторная выдача одного кода блокируется.
- Возврат оформляется через owned refund request; решение и исполнение — только MFA-admin с audit trail.

## Стек

Python · FastAPI · PostgreSQL production / SQLite dev · Alembic · Redis · vanilla JS · `segno`. PostgreSQL repositories используют psycopg DB-API adapter; schema изменяется только versioned migrations.

## Запуск

```bash
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements-dev.lock
uvicorn app.main:app --reload      # http://localhost:8000 · /openapi.json — API schema
pytest                              # SQLite unit/security + optional PostgreSQL integration
DATABASE_URL=postgresql://... alembic upgrade head
```

База наполняется демо-данными Астаны при первом старте (6 заведений, 7 боксов).

## Про оплату (важно)

Backend поддерживает `disabled`, development-only `demo` и Stripe Checkout.
Production с `demo` не стартует; `disabled` оставляет каталог доступным, но
покупки fail-closed выключены. Stripe flow резервирует
inventory как `payment_pending`, создаёт idempotent Checkout Session и переводит
заказ в `paid` только после подписанного/reconciled webhook. Для live запуска сначала
проверь доступность Stripe merchant/Connect для юридической структуры в Казахстане;
локальный Kaspi остаётся отдельным provider roadmap.

## Дорожная карта (после пилота)

- **Kaspi Pay/QR** — реальная оплата.
- Карта + геолокация, пуши «появились боксы рядом», избранные точки.
- Реферальная программа, промокоды, рейтинг боксов.
- Комиссия 5–12% с заказа после валидации спроса.

> MVP проверяет 3 гипотезы: **supply** (партнёры публикуют), **demand**
> (люди покупают), **operations** (бронь/выдача без хаоса) — прежде чем вкладываться в полноценное приложение.

## Запуск в продакшен (чеклист)

1. **Деплой бэкенда** — Render → New → Blueprint → этот репозиторий (`render.yaml`).
2. **Переменные окружения** — заполнить по [.env.example](.env.example):
   `YUMMY_SECRET_KEY`, отдельный `YUMMY_DATA_KEY`, `YUMMY_ENV=production`,
   `YUMMY_ALLOWED_HOSTS` и `YUMMY_CORS_ORIGINS`.
3. **Админ-доступ** — создать операторской командой в Render Shell:
   `python tools/create_admin.py owner@example.com`. CLI выдаст TOTP URI и
   одноразовые recovery codes; admin API требует MFA claim. Публичная регистрация
   никогда не выдаёт роль admin.
4. **Персонал и партнёры** — покупатель не видит staff/admin навигацию. MFA-admin
   создаёт одноразовую 7-дневную ссылку для owner/manager/cashier; публичная partner
   регистрация в production запрещена. Cashier выдаёт заказы, но не публикует боксы.
   Production UI обслуживается backend same-origin; Pages — только browser-demo.
5. **Оплата** — после регистрации мерчанта Kaspi вписать `KASPI_SERVICE_ID`
   в `app/static/index.html` (кнопка Kaspi появится сама).
6. **Telegram-вход/уведомления** — токен от @BotFather в `TELEGRAM_BOT_TOKEN`.

Разработка: `make help` (dev / test / docs / seed / zip).

Partner billing: merchant credentials шифруются AES-256-GCM, payment account должен
быть active, а комиссия фиксируется integer basis points в immutable ledger.

VPS deployment готов в `deploy/`: Caddy, Docker Compose, internal Redis, health
checks, `.env` template и deploy script. `tools/check_production.py` проверяет
Supabase revision/таблицы/Redis без вывода secrets.

Horizontal deployment: задай `REDIS_URL` — включатся атомарные distributed limits;
при configured Redis outage limiter fail-closed возвращает `503`, а не деградирует.

Security baseline, STRIDE и честная ASVS gap-матрица:
[SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md). Технический roadmap,
Mermaid-схемы и pentest checklist: [SECURITY_IMPLEMENTATION_PLAN.md](SECURITY_IMPLEMENTATION_PLAN.md).
