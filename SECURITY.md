# Yummy — аудит безопасности и функционала

Актуальная trust-boundary схема, STRIDE и честная ASVS gap-матрица находятся в
[SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md).

Разбор по присланным open-source проектам: что взято, что уже было, что осталось.

## Источники
**Безопасность:** [API-Security-Checklist](https://github.com/shieldfy/API-Security-Checklist),
[awesome-security](https://github.com/sbilly/awesome-security),
[aspnet/Security](https://github.com/aspnet/Security) (.NET),
[spring-security-oauth](https://github.com/spring-attic/spring-security-oauth) (Java),
[xapax/security](https://github.com/xapax/security).
**Фудтех/TGTG:** [enatega multivendor](https://github.com/enatega/food-delivery-multivendor),
[enatega singlevendor](https://github.com/enatega/food-delivery-singlevendor),
[Tarikul flutter UI](https://github.com/Tarikul711/flutter-food-delivery-app-ui),
[TooGoodToGoNotifier](https://github.com/Viincenttt/TooGoodToGoNotifier),
[tgtg_client](https://github.com/Azzeccagarbugli/tgtg_client).

> Код .NET/Java/Flutter/React-Native **не портировался** (несовместимый стек) —
> перенесены применимые **паттерны и чеклисты**.

## Аудит по API-Security-Checklist

| Пункт чеклиста | Статус в Yummy |
|---|---|
| Не Basic Auth, стандартная авторизация | ✅ JWT (HS256, stdlib) |
| Не изобретать хеш пароля | ✅ Argon2id через `argon2-cffi`; legacy PBKDF2 только для миграции |
| Max Retry / jail на логине | ✅ rate-limit 6/мин на /auth/*; 8/мин на /orders |
| Шифрование чувствительных данных | ✅ пароли только хешем; хеш не в ответе |
| Throttling против DDoS/brute-force | ✅ local guards + optional Redis atomic distributed limits, fail-closed |
| HTTPS + HSTS | ✅ HSTS-заголовок; TLS даёт Pages/Render |
| **Private endpoints за аутентификацией** | ✅ deny-by-default: `require_role` на /boxes, /redeem, /partner/me/*, /admin/*; env-флаг не может открыть API |
| `/me/orders` вместо `/user/{id}/orders` | 🟡 есть /partners/{id} (id — UUID); /auth/me реализован |
| UUID вместо auto-increment | ✅ uuid4 для заказов и пользователей |
| Валидация content-type / входа | ✅ Pydantic; FastAPI требует JSON |
| Нет секретов в URL | ✅ логин/пароль в теле POST |
| Параметризованные запросы (нет SQLi) | ✅ sqlite3 с плейсхолдерами |
| `X-Content-Type-Options: nosniff` | ✅ middleware |
| `X-Frame-Options: deny` | ✅ middleware (DENY) |
| `Content-Security-Policy` | ✅ middleware |
| **Убрать fingerprint `Server`** | ✅ **добавлено:** uvicorn `--no-server-header` |
| Force content-type ответа | ✅ FastAPI JSON |
| Не возвращать секреты | ✅ pw_hash никогда не в ответе |
| Правильные HTTP-статусы | ✅ 201/401/403/409/422/429 |
| DEBUG off | ✅ FastAPI без debug; /docs можно скрыть в проде |
| Тесты (unit/integration) | ✅ security suite: миграции, BOLA/tenant isolation, PII-redaction, request policy и просроченные окна |
| Централизованные логи, без секретов | ✅ аудит-лог logging (register/login/IP, без паролей) |
| security.txt | ✅ **добавлено:** /.well-known/security.txt |
| CORS без wildcard+credentials | ✅ явные origin из env |

## Что уже было из фудтех-функционала (enatega/TGTG)
Сюрприз-бокс (magic bag), бронь+окно выдачи, QR/код, no-show/возврат, избранные
кофейни (♥), рейтинги, поиск, история заказов, карта с точками, категории,
фильтры (район/сеть/«забрать сейчас»), эко-вклад, passwordless-вход (Telegram),
PWA-установка, маршрут в 2ГИС, deep-link на бокс, регистрация email+пароль.

## Прод-этап (нужны внешние сервисы/ключи — отложено)
- **Уведомления о появлении боксов** (ключевая фича TGTG-нотификаторов): нужен
  бот/почта — Telegram-бот (токен от @BotFather) + рассылка «твоя Zebra выставила
  боксы». Инфраструктура (auth_telegram.py) готова.
- **Реальные платежи** — Kaspi Pay/QR (deep-link-слот готов).
- **Social-auth** Google/Apple (enatega) — нужны OAuth-ключи.
- **Real-time трекинг/чат** — WebSocket + сервер.
- **Sentry/мониторинг** (enatega) — нужен DSN.

## Пак «БД и безопасность» (доделка)

**БД (PostgreSQL production / SQLite dev):**
- WAL + busy_timeout=5000 + synchronous=NORMAL — параллельные запросы без
  «database is locked»; foreign keys включены, схема с REFERENCES.
- Индексы под реальные запросы: boxes(partner,status), orders(partner/user/status).
- Production подключается только через PostgreSQL `DATABASE_URL`; SQLite разрешён
  лишь dev/test и сохраняет WAL/busy-timeout fallback.
- Schema — versioned Alembic migrations; Render применяет их pre-deploy.
- `make backup` — только SQLite dev; production backup/PITR делегирован managed PostgreSQL.

**Безопасность:**
- **Отзыв сессий**: смена пароля инкрементирует `users.token_ver` → все ранее
  выданные JWT (в т.ч. украденные) мгновенно мертвы; текущему устройству
  возвращается свежий токен. Проверено live: 200 → 401 → 200.
- **Fail-fast конфиг**: `YUMMY_ENV=production` с dev-секретом — сервер
  отказывается стартовать с ясной ошибкой; private API защищён независимо от env.
- Rate-limiter: защита от роста памяти (purge стухших IP при >4096 записей).
- Аудит возвратов админа (кто/какой заказ/IP).
- Bandit-скан: 0 issues (единственный сигнал — намеренный dev-сентинел, nosec).
- Секретов в репозитории нет (grep по паттернам токенов — чисто).

**Object-level authorization и PII:**
- партнёрский аккаунт получает неизменяемый `partner_id`; private API использует
  `/partner/me/*` и сверяет tenant на создании бокса, чтении заказов и выдаче;
- legacy `/partners/{id}/orders` оставлен только как authenticated/deprecated и
  также проходит tenant guard;
- гостевой `GET /orders/{code}` возвращает отдельную redacted-модель без имени,
  телефона, внутренних id и `partner_id`;
- коды выдачи — `YM-XXXXX-XXXXX`, 50 бит CSPRNG-энтропии, без неоднозначных символов;
- публичная регистрация не может выдать admin; bootstrap — только операторским
  `tools/create_admin.py`, с отзывом старых сессий;
- согласие с документами обязательно валидируется сервером, дата и версия
  сохраняются в `users.terms_accepted_at/terms_version`.

## Карта по Sentinel-спеке (честно: что есть, чего нет)

Принцип из самой спеки: **не заявлять функции, которых нет.**

| Sentinel-пункт | Статус |
|---|---|
| Короткий access-токен (15 мин) | ✅ `_TOKEN_TTL = 15 мин` |
| Refresh-токен с ротацией | ✅ SHA-256 hash, atomic rotation, token families и reuse detection с отзывом семейства |
| Выйти со всех устройств | ✅ /auth/logout-all (token_ver+1 + отзыв всех refresh) |
| Argon2id | ✅ 64 MiB / 3 прохода / parallelism 4; legacy PBKDF2 совместим и rehash'ится после входа |
| Пароли не хранятся | ✅ только солёный хеш |
| RBAC | ✅ customer / partner / admin (`require_role`) |
| Brute force / credential stuffing | ✅ rate-limit по IP + jail по email (5 неудач → 10 мин) |
| Admin MFA | ✅ обязательный TOTP/recovery; AES-256-GCM seed; replay counter; JWT/refresh assurance |
| Partner trust | ✅ pending-by-default; MFA admin approval; suspension отзывает sessions/inventory |
| Refund abuse | ✅ owner-only single request; issued-order guard; MFA admin decision; atomic inventory/order update |
| SQLi / XSS / Clickjacking | ✅ параметризованный SQL / esc()+CSP / X-Frame-Options DENY |
| CSRF | ✅ Browser: SameSite=Strict + double-submit token + Origin; Bearer API cookie-independent |
| Аудит: регистрация/вход/смена пароля/заказы/возвраты | ✅ логируются с IP, без паролей |
| Privacy: скачать свои данные | ✅ GET /me/export (профиль + заказы, JSON) |
| Privacy: удалить аккаунт | ✅ DELETE /me — вход невозможен, PII в заказах обезличен (проверено) |
| Резервные копии | ✅ make backup (шифрование бэкапов — нет, не заявляем) |
| Email verification/recovery | ✅ hashed single-use tokens, expiry/reissue, non-enumerating forgot; delivery provider external |
| OAuth / WebAuthn / CAPTCHA / гео-детект / login alerts | ❌ следующий этап |
| TLS 1.3 / AES-256 at rest | 🟡 TLS даёт хостинг; шифрование БД (SQLCipher) — прод-этап, не заявляем |

## Пак «AI-фичи» (описания, рекомендации, отзывы+модерация, скрипт продаж)

Принцип тот же: **не заявлять AI там, где его нет.** Интеграция — сырой
`httpx`-клиент к Anthropic API (`app/ai.py`), без агентных фреймворков
(LangChain/agno/crewAI и т.п.) — меньше зависимостей и предсказуемое
поведение без ключа.

| Фича | Без `ANTHROPIC_API_KEY` | С ключом |
|---|---|---|
| Описание бокса (`POST /ai/describe-box`) | ✅ детерминированный шаблон (`ai:false` в ответе) | AI-текст (`ai:true`) |
| Рекомендации (`GET /me/recommendations`) | ✅ всегда — это **не AI**, детерминированный скоринг по истории покупок (категория×2 + партнёр×3), без AI не деградирует | тот же алгоритм (AI не участвует) |
| Модерация отзыва (`POST /partners/{id}/reviews`) | ✅ эвристика: мат-лист, спам-ссылки (`http/www/t.me/@handle`), капслок >70%, повтор символов | эвристика + AI поверх (эвристика остаётся первым фильтром) |
| Скрипт продаж (`tools/generate_pitch.py`) | ✅ шаблон по тексту из SALES.md, персонализирован именем/адресом | AI-текст, другой при каждом вызове |

**Почему не 501, а фолбэк:** в отличие от Kaspi/Telegram-слотов (которые
честно отдают 501 без ключа, т.к. без реальной интеграции работать не
могут), у всех четырёх AI-фич есть осмысленный офлайн-эквивалент — фича не
исчезает, а становится проще.

**Безопасность отзывов:** заказ на владение проверяется через
`store.user_orders(user.id)` (тот же `WHERE user_id=?`, что и в
`/me/orders`) — id заказа из тела запроса никогда не доверяется напрямую;
отзыв разрешён только по заказу в статусе `issued` (реально выдан по коду) и
не более одного на заказ. Rate-limit на AI-эндпоинты отдельный и строже
(6/60 сек), чем на заказы (8/60 сек) — дороже по деньгам при реальном ключе.

**Не заявляем:** AI-модерация не «финальная» — это фильтр перед публикацией,
живой модератор всё ещё нужен для спорных случаев; описания и питчи с AI не
проверяются на фактическую точность (партнёр видит текст перед публикацией).

## Правовой слой (пункт «правовая база не закрыта»)

Однострочные заглушки заменены содержательными **рабочими шаблонами** (в репо
`legal/`, в приложении — футер → «Документы»). **Не заверены юристом** — перед
публичным запуском обязательна вычитка юристом РК.

- `legal/oferta.md` — публичная оферта (агентская модель, оплата, выдача,
  возвраты, ответственность, права по Закону РК «О защите прав потребителей»).
- `legal/privacy.md` — политика по Закону РК «О персональных данных» № 94-V
  (какие данные, согласие, передача только по заказу, права пользователя).
- `legal/partner-agreement.md` — агентский договор с заведением (комиссия,
  выплаты по средам, обязанности, споры, расторжение).
- `legal/food-safety.md` — стандарты пищевой безопасности (что продавать,
  хранение, аллергены, чек-лист, ответственность заведения).

**Согласие на обработку ПДн (ст. 8 № 94-V)** — обязательный чекбокс при
регистрации (онбординг и лендинг): без галочки регистрация блокируется. У
заведения дополнительно — принятие договора и стандартов пищевой безопасности.
Проверено live: без согласия — ошибка и аккаунт не создаётся.
