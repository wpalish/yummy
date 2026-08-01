#!/usr/bin/env bash
# Переезд Yummy на Fly.io — всё, что можно автоматизировать.
#
# Что нужно от вас ДО запуска:
#   1) flyctl auth login          (аккаунт Fly)
#   2) Render → Environment → Export → сохранить файл рядом как render.env
#
# Запуск:  ./deploy-fly.sh
#
# Скрипт идемпотентный: повторный запуск не ломает уже созданное.
set -euo pipefail

APP="yummy-astana"
REGION="waw"
ENV_FILE="${1:-render.env}"
FLY="$HOME/.fly/bin/flyctl"
[ -x "$FLY" ] || FLY="$(command -v flyctl || true)"

say()  { printf '\n\033[1m▸ %s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
die()  { printf '  \033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

# ── 0. Предполётные проверки ────────────────────────────────────────────────
say "Проверяю окружение"
[ -n "$FLY" ] && [ -x "$FLY" ] || die "flyctl не найден. Установите: curl -L https://fly.io/install.sh | sh"
ok "flyctl $($FLY version | awk '{print $2}')"

$FLY auth whoami >/dev/null 2>&1 || die "Не выполнен вход. Сделайте: flyctl auth login"
ok "вход как $($FLY auth whoami 2>/dev/null)"

[ -f fly.toml ] || die "Запускать из корня репозитория (нет fly.toml)"
ok "fly.toml на месте"

[ -f "$ENV_FILE" ] || die "Нет файла $ENV_FILE. Render → Environment → Export, сохраните сюда."
ok "переменные: $ENV_FILE"

# ── 1. Приложение ───────────────────────────────────────────────────────────
say "Создаю приложение"
if $FLY status --app "$APP" >/dev/null 2>&1; then
  ok "приложение $APP уже существует — пропускаю"
else
  $FLY launch --no-deploy --copy-config --name "$APP" --region "$REGION" --yes
  ok "создано: $APP ($REGION)"
fi

# ── 2. Секреты ──────────────────────────────────────────────────────────────
# Переносим только то, что реально нужно рантайму. PYTHON_VERSION и YUMMY_DB_PATH
# специфичны для Render; YUMMY_ENFORCE_AUTH/CORS/PUBLIC_URL уже заданы в fly.toml.
say "Переношу секреты"
KEEP='^(DATABASE_URL|YUMMY_SECRET_KEY|YUMMY_CRED_KEY|YUMMY_ADMIN_EMAILS|YUMMY_PAYMENT_MODE|APIPAY_API_KEY|APIPAY_WEBHOOK_SECRET|YUMMY_RESEND_KEY|YUMMY_SMTP_FROM|TELEGRAM_BOT_TOKEN|YUMMY_ORDERS_CHAT_ID|YUMMY_TG_CHANNEL)='

TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
grep -E "$KEEP" "$ENV_FILE" > "$TMP" || true
COUNT=$(wc -l < "$TMP" | tr -d ' ')
[ "$COUNT" -gt 0 ] || die "В $ENV_FILE не нашлось нужных переменных — проверьте файл"

# Критично: без этих двух слетят сессии и 2FA админа
for req in DATABASE_URL YUMMY_SECRET_KEY YUMMY_CRED_KEY; do
  grep -q "^$req=" "$TMP" || die "В $ENV_FILE нет $req — без него переезд сломает вход"
done

$FLY secrets import --app "$APP" --stage < "$TMP"
ok "перенесено переменных: $COUNT (значения не выводятся)"
printf '    '; cut -d= -f1 "$TMP" | tr '\n' ' '; echo

# ── 3. Деплой ───────────────────────────────────────────────────────────────
say "Разворачиваю"
$FLY deploy --app "$APP" --remote-only
ok "деплой завершён"

# ── 4. Проверка ─────────────────────────────────────────────────────────────
say "Проверяю здоровье"
URL="https://$APP.fly.dev"
for i in $(seq 1 10); do
  BODY=$(curl -fsS "$URL/health" 2>/dev/null) && break
  printf '  ждём запуска (%s/10)…\n' "$i"; sleep 6
done
[ -n "${BODY:-}" ] || die "Сервис не отвечает на $URL/health — смотрите: flyctl logs --app $APP"
ok "health: $BODY"

# Сверяем с Render — база одна, цифры должны совпасть
OLD=$(curl -fsS https://yummy-astana.onrender.com/health 2>/dev/null || echo '')
[ -n "$OLD" ] && printf '  Render: %s\n' "$OLD"

cat <<EOF

────────────────────────────────────────────────────────────
Готово. Новый адрес: $URL

⚠️  ОСТАЛСЯ ОДИН РУЧНОЙ ШАГ — без него оплата тихо сломается:

    Кабинет ApiPay → Настройки → Подключение → ключ «Yummy сайт»
    Адрес уведомлений заменить на:

        $URL/webhooks/apipay

    Проверить: создать счёт → «Симулировать» → в логах должно
    появиться «audit: apipay paid»:  flyctl logs --app $APP

Render пока НЕ выключайте — пусть работает как запасной, пока
не убедитесь, что оплата и почта идут через новый адрес.
────────────────────────────────────────────────────────────
EOF
