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
