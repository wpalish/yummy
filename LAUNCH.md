# 🚀 Запуск Yummy в прод — runbook (15 минут)

Код **готов**. Ниже — операционные шаги, которые может сделать только владелец
(доступы к Render / Telegram / Kaspi). Делать по порядку, отмечая галочки.

Живое сейчас: сайт https://wpalish.github.io/yummy · API https://yummy-astana.onrender.com
· бот @yummy_astana_bot · репо github.com/wpalish/yummy.

---

## 0. Обязательное: задеплоить накопленные изменения бэкенда

В `main.py` накопились изменения (CSP-nonce, Telegram-канал), которых ещё нет в проде.

- [ ] `dashboard.render.com` → сервис **yummy-astana** (`srv-d9atc2beo5us73dhq3f0`)
- [ ] **Manual Deploy → Deploy latest commit**
- [ ] Дождаться `Live`, проверить: `curl -s https://yummy-astana.onrender.com/health`
      → `{"status":"ok",...}`

> Автодеплоя нет (репо подключён по public-URL) — деплой всегда вручную после пуша.

---

## 1. Секретный ключ сессий (критично для безопасности)

Без него прод-режим **не стартует** (fail-fast), а с дефолтным — токены подделываемы.

- [ ] Сгенерировать: `python -c "import secrets;print(secrets.token_hex(32))"`
- [ ] Render → **Environment** → `YUMMY_SECRET_KEY` = (вставить)
- [ ] Заодно включить прод-строгость: `YUMMY_ENFORCE_AUTH=1` (выключает Swagger,
      требует секрет), `YUMMY_ALLOWED_HOSTS=yummy-astana.onrender.com`

---

## 2. Telegram-бот: уведомления о новых боксах

- [ ] Токен у @BotFather → Render → `TELEGRAM_BOT_TOKEN` = `123456:AA...`
- [ ] Секрет webhook: `python -c "import secrets;print(secrets.token_hex(16))"`
      → Render → `TELEGRAM_WEBHOOK_SECRET` = (вставить)
- [ ] **Manual Deploy** (чтобы env применился), дождаться `Live`
- [ ] Зарегистрировать webhook (локально, с токеном в окружении):
      ```
      TELEGRAM_BOT_TOKEN=<токен> YUMMY_PUBLIC_API=https://yummy-astana.onrender.com \
        python -m app.telegram_bot set-webhook
      ```
- [ ] Проверка: написать боту `/start` → должно прийти приветствие; `/boxes` → список.

---

## 3. Telegram-канал-витрина (двигатель охвата)

Новые боксы авто-постятся в публичный канал с кнопкой «Забрать бокс».

- [ ] Создать канал в Telegram (напр. `@yummy_astana`), сделать **публичным**
- [ ] Добавить **@yummy_astana_bot админом** канала с правом «Публикация сообщений»
- [ ] Render → `YUMMY_TG_CHANNEL` = `@yummy_astana` → **Manual Deploy**
- [ ] Проверка связи: `TELEGRAM_BOT_TOKEN=<токен> YUMMY_TG_CHANNEL=@yummy_astana \
        python -m app.notify channel-test` → `ok`
- [ ] Ссылка на канал сама появится в футере и на успех-экране (Render-версия).
- [ ] Для публичного сайта (Pages) — запечь ссылку в статику и запушить:
      ```
      YUMMY_TG_CHANNEL=@yummy_astana YUMMY_PAGES_API_BASE=https://yummy-astana.onrender.com \
        make docs && git add docs && git commit -m "chore: канал в Pages" && git push
      ```

---

## 4. AI-фичи (опционально — работают и без ключа, на фолбэках)

- [ ] Render → `ANTHROPIC_API_KEY` = `sk-ant-...` → **Manual Deploy**
- [ ] Без ключа: описания боксов и модерация отзывов деградируют на детерминированные
      фолбэки — сайт не ломается.

---

## 5. Оплата (Kaspi) — когда будет мерчант-аккаунт

Сейчас оплата в **демо-режиме** (честно подписано в UI). Реальную включить нельзя
без Kaspi Business.

- [ ] Оформить Kaspi Business мерчант (это шаг владельца бизнеса)
- [ ] Получить `service_id` / API мерчанта
- [ ] Прописать во фронте `KASPI_SERVICE_ID` — кнопка «Оплатить через Kaspi»
      появится автоматически (слот уже в коде, `openBox()`).
- [ ] Kaspi webhook для подтверждения оплаты → `POST /orders/confirm-payment`
      (эндпоинт готов, ждёт подписанного вебхука вместо ручной кнопки).

---

## 6. Финальная проверка «всё живо»

- [ ] `curl -sD- https://yummy-astana.onrender.com/ | grep -i content-security`
      → в `script-src` есть `'nonce-...'`, **нет** `'unsafe-inline'`.
- [ ] Открыть https://wpalish.github.io/yummy — заказать бокс как гость, получить код+QR.
- [ ] Партнёром: зарегистрироваться, создать бокс → проверить пост в канал.
- [ ] `/boxes` боту → список; новый бокс → пришло уведомление подписчику.

---

## Что НЕ требует владельца (уже сделано в коде)

- ✅ Полный флоу заказ→оплата→код→QR, отмена/возврат по коду (IDOR-safe).
- ✅ Партнёрка: боксы, шаблоны, комиссия, payment-аккаунты.
- ✅ Админка: заказы, статистика, возвраты.
- ✅ Безопасность: CSP без unsafe-inline, PBKDF2 600k, rate-limit, TrustedHost,
      lockout, JWT-ревокация, полный набор security-заголовков.
- ✅ Telegram: бот (webhook) + канал-витрина + личные уведомления с кнопками.
- ✅ PWA (установка на телефон, оффлайн-коды), KZ/RU локаль, Supabase Postgres.
- ✅ 108 тестов зелёные.

> Held-back честно: реальная Kaspi-оплата (нужен мерчант) и Instagram/TikTok
> (подписаны «скоро»). Всё остальное — рабочее.
