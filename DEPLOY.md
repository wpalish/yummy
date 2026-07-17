# Деплой Yummy: VPS production и Render reference

Рекомендуемый production путь — `deploy/docker-compose.production.yml` на VPS:
Caddy выдаёт TLS, FastAPI закрыт внутренней сетью, Redis не публикует порт, ARQ
worker работает отдельным container, а PostgreSQL находится в Supabase. `/health`
fail-closed проверяет worker heartbeat при `YUMMY_REQUIRE_WORKER=1`.
Скопируй `deploy/env.production.example` в
`.env.production`, заполни secrets локально и запусти `deploy/deploy.sh`.

`render.yaml` остаётся reference-вариантом managed deployment.

## Шаг 1. Аккаунт Render
1. Открой **render.com** → **Get Started** → войди **через GitHub** (тот же
   аккаунт `wpalish`).
2. Разреши Render доступ к репозиториям (можно только к `yummy`).

## Шаг 2. Blueprint (один клик)
1. В Render: **New +** → **Blueprint**.
2. Выбери репозиторий **wpalish/yummy** → Render найдёт `render.yaml`.
3. **Apply**. Render создаст web-сервис `yummy-astana` и подставит все переменные
   (включая случайный `YUMMY_SECRET_KEY`).
4. Жди ~2–4 минуты (сборка + старт). Статус станет **Live**.

## Шаг 3. Проверка
Открой в браузере (URL вида `https://yummy-astana.onrender.com`):
- `…/health` → `{"status":"ok"}` — сервер жив, без внутренних счётчиков.
- `…/docs` → `404` в production (Swagger не публикуется наружу).
- `…/` → сам сайт Yummy с бэкендом.

Если Render выдал hostname с суффиксом или подключён custom domain, добавь его в
`YUMMY_ALLOWED_HOSTS`, иначе Host-header middleware ожидаемо вернёт `400`.

## Шаг 4. Создать администратора
Не повышай роль через публичную регистрацию: без подтверждения email это позволило
бы захватить админку. Открой **Render Shell** сервиса и выполни:
```bash
python tools/create_admin.py owner@example.com
```
Пароль вводится скрыто и не попадает в shell history. Команда также один раз
печатает `otpauth://` URI, encrypted-at-rest TOTP secret и 10 одноразовых recovery
codes — сохрани их офлайн. Admin login без MFA не выдаёт control-plane session.
Если аккаунт уже существует, он повышается до `admin`, старые сессии отзываются.
Ротация фактора: `python tools/create_admin.py owner@example.com --reset-mfa`.

### Transactional email

Для реальной email verification/password recovery настрой Resend:
`YUMMY_EMAIL_MODE=resend`, `RESEND_API_KEY`, `YUMMY_EMAIL_FROM` и HTTPS
`YUMMY_PUBLIC_URL`. В `disabled` регистрация остаётся unverified; MFA-admin может
подтвердить email вручную с обязательной audit-причиной. Raw verification/reset
tokens в БД и логах не сохраняются.

После входа открой Admin → «Заявки заведений». Новое заведение имеет статус
`pending` и не может публиковать/выдавать до verified email + `approved`.
`suspended/rejected` мгновенно отзывает его сессии и снимает active inventory.

## Шаг 5. Production frontend — только same-origin

Открывай приложение прямо на URL backend (`https://yummy-astana.onrender.com/`)
или привяжи к нему custom domain. Вход работает через `Secure + HttpOnly +
SameSite=Strict` cookies и double-submit CSRF; access/refresh токены недоступны JS.

`wpalish.github.io/yummy` остаётся **изолированной browser-only демкой** без
доступа к production API. `make docs` намеренно отклоняет
`YUMMY_PAGES_API_BASE`: cross-origin Pages потребовал бы ослабить cookie/CORS
границу. Проверка production: регистрация на backend URL → `/session/me` отвечает
профилем на том же origin, а mutation без `X-CSRF-Token` получает `403`.

---

## Важно про бесплатный план
- **Спин-даун**: free-сервис засыпает после 15 мин простоя; первый заход после сна
  грузится ~50 сек (потом быстро). Для показа кофейне — ок; для потока клиентов —
  апгрейд.
- **PostgreSQL plan limits**: проверь срок жизни free DB, storage, backup/PITR и
  connection limits в актуальном тарифе Render. Для real traffic нужен план с
  гарантированным retention, backup и достаточным connection budget.

## Redis для нескольких replicas

При horizontal scaling задай `REDIS_URL` и отдельный `YUMMY_RATE_LIMIT_KEY`.
Auth/orders/redeem/general budgets считаются атомарно общими для всех instances.
Если configured Redis недоступен, API fail-closed отвечает `503 + Retry-After`;
локальные endpoint limits остаются вторым слоем.

## PostgreSQL и migrations

`render.yaml` создаёт managed `yummy-db` и передаёт `DATABASE_URL`. Перед каждым
release Render выполняет `alembic upgrade head` как `preDeployCommand`, а replicas
стартуют только после успешной migration. В production SQLite запрещён fail-fast
проверкой. Для локальной PostgreSQL:

```bash
export DATABASE_URL=postgresql://yummy:password@localhost:5432/yummy
alembic upgrade head
uvicorn app.main:app
```

Schema нельзя менять startup-DDL или вручную: только новая Alembic revision.
`YUMMY_DB_POOL_MAX × replicas` должен укладываться в connection limit managed DB;
pool ленивый, bounded, с 5-секундным checkout timeout и rollback при exception.
Каждое соединение получает `statement_timeout=5s`, `lock_timeout=2s` и
`idle_in_transaction_session_timeout=10s`. `/health` проверяет DB readiness,
`/live` — только процесс; pool saturation доступен лишь MFA-admin.
Managed backup/PITR настраивается у DB provider; `make backup` остаётся только для
локального SQLite fallback.

## Переменные окружения (уже в render.yaml)
| Переменная | Значение | Зачем |
|---|---|---|
| `YUMMY_SECRET_KEY` | генерится Render | подпись JWT |
| `YUMMY_DATA_KEY` | отдельное generated value | AES-256-GCM для MFA secrets |
| `YUMMY_ENV` | `production` | fail-fast при небезопасном конфиге |
| `YUMMY_CORS_ORIGINS` | `https://wpalish.github.io` | доступ витрины к API |
| `YUMMY_ALLOWED_HOSTS` | hostname Render/custom domain | Host Header allowlist |
| `YUMMY_MAX_REQUEST_BYTES` | `65536` | лимит JSON body |
| `YUMMY_EMAIL_MODE` | `disabled` или `resend` | transactional email adapter |
| `RESEND_API_KEY` / `YUMMY_EMAIL_FROM` | secret/sender | verification и recovery |
| `YUMMY_PUBLIC_URL` | HTTPS origin | безопасные action links |
| `DATABASE_URL` | managed PostgreSQL connection string | production data plane |
| `YUMMY_DB_PATH` | local only | SQLite dev/test fallback |
| `TELEGRAM_BOT_TOKEN` | _(пусто)_ | добавишь для входа через Telegram |

Секрет можно и задать вручную (Render → сервис → Environment):
`YUMMY_SECRET_KEY` = сгенерируй `python -c "import secrets;print(secrets.token_hex(32))"`.
