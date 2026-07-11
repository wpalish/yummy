# Yummy — аудит безопасности и функционала

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
| Не изобретать хеш пароля | ✅ PBKDF2-HMAC-SHA256, соль+200k, constant-time |
| Max Retry / jail на логине | ✅ rate-limit 6/мин на /auth/*; 8/мин на /orders |
| Шифрование чувствительных данных | ✅ пароли только хешем; хеш не в ответе |
| Throttling против DDoS/brute-force | ✅ in-memory rate-limit по IP |
| HTTPS + HSTS | ✅ HSTS-заголовок; TLS даёт Pages/Render |
| **Все эндпоинты за аутентификацией** | ✅ **добавлено:** ролевые `require_role` на /boxes, /redeem, /admin/* (env `YUMMY_ENFORCE_AUTH=1`) |
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
| Тесты (unit/integration) | ✅ 31 тест (крипто/JWT/флоу/заголовки/ролевой доступ) |
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

**БД (SQLite production-grade):**
- WAL + busy_timeout=5000 + synchronous=NORMAL — параллельные запросы без
  «database is locked»; foreign keys включены, схема с REFERENCES.
- Индексы под реальные запросы: boxes(partner,status), orders(partner/user/status).
- Путь к БД — env `YUMMY_DB_PATH` (persistent-диск на хостинге).
- `make backup` — консистентный бэкап через официальный SQLite backup API
  (безопасен при живом WAL), хранит последние 14 копий.

**Безопасность:**
- **Отзыв сессий**: смена пароля инкрементирует `users.token_ver` → все ранее
  выданные JWT (в т.ч. украденные) мгновенно мертвы; текущему устройству
  возвращается свежий токен. Проверено live: 200 → 401 → 200.
- **Fail-fast конфиг**: `YUMMY_ENFORCE_AUTH=1` с dev-секретом — сервер
  отказывается стартовать с ясной ошибкой (проверено).
- Rate-limiter: защита от роста памяти (purge стухших IP при >4096 записей).
- Аудит возвратов админа (кто/какой заказ/IP).
- Bandit-скан: 0 issues (единственный сигнал — намеренный dev-сентинел, nosec).
- Секретов в репозитории нет (grep по паттернам токенов — чисто).

## Карта по Sentinel-спеке (честно: что есть, чего нет)

Принцип из самой спеки: **не заявлять функции, которых нет.**

| Sentinel-пункт | Статус |
|---|---|
| Короткий access-токен (15 мин) | ✅ `_TOKEN_TTL = 15 мин` |
| Refresh-токен с ротацией | ✅ /auth/refresh; в БД только SHA-256-хеш; использованный сгорает (проверено live) |
| Выйти со всех устройств | ✅ /auth/logout-all (token_ver+1 + отзыв всех refresh) |
| Argon2id | ❌ **не заявляем** — PBKDF2-HMAC-SHA256 600k итераций (OWASP-уровень), без нативных зависимостей; старые хеши совместимы |
| Пароли не хранятся | ✅ только солёный хеш |
| RBAC | ✅ customer / partner / admin (`require_role`) |
| Brute force / credential stuffing | ✅ rate-limit по IP + jail по email (5 неудач → 10 мин) |
| SQLi / XSS / Clickjacking | ✅ параметризованный SQL / esc()+CSP / X-Frame-Options DENY |
| CSRF | ✅ N/A — cookies не используются (токен в заголовке) |
| Аудит: регистрация/вход/смена пароля/заказы/возвраты | ✅ логируются с IP, без паролей |
| Privacy: скачать свои данные | ✅ GET /me/export (профиль + заказы, JSON) |
| Privacy: удалить аккаунт | ✅ DELETE /me — вход невозможен, PII в заказах обезличен (проверено) |
| Резервные копии | ✅ make backup (шифрование бэкапов — нет, не заявляем) |
| Email verification / OAuth / 2FA / CAPTCHA / гео-детект / уведомления о входе | ❌ **не реализовано** — требуют внешних сервисов (SMTP, OAuth-ключи, SMS). Заготовка: Telegram-вход |
| TLS 1.3 / AES-256 at rest | 🟡 TLS даёт хостинг; шифрование БД (SQLCipher) — прод-этап, не заявляем |
