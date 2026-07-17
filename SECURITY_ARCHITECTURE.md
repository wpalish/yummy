# Yummy — security architecture и ASVS roadmap

Дата baseline: 2026-07-14. Цель: defense in depth, secure-by-default и Zero Trust
для пилота. Этот документ — **матрица контроля, а не сертификат соответствия**.
OWASP ASVS Level 3 подтверждается только после threat modeling, evidence review,
инфраструктурного аудита, DAST и независимого penetration test. Project-specific
ТЗ, Mermaid-схемы, оценки и pentest checklist: [SECURITY_IMPLEMENTATION_PLAN.md](SECURITY_IMPLEMENTATION_PLAN.md).

## 1. Trust boundaries

```text
Internet
  │  (untrusted client/IP/headers/body)
  ▼
Cloudflare / WAF / Turnstile        EXTERNAL — требуется настройка аккаунта
  │  TLS termination, bot/DDoS
  ▼
Render edge / reverse proxy         EXTERNAL — managed infrastructure
  │
  ▼
FastAPI request policy              IMPLEMENTED — Host/body/type/schema/rate limit
  │
  ├── Public catalog                no PII
  ├── Customer tenant               JWT subject ownership
  ├── Partner tenant                partner_id + owner_user_id guard
  └── Admin plane                   RBAC + mandatory TOTP; WebAuthn target
  │
  ▼
Managed PostgreSQL private data plane  psycopg transactions + Alembic; PITR external
  │
  ▼
Encrypted offsite immutable backup  EXTERNAL — not provided by repository
```

Ни один `partner_id`, `order_id`, роль, цена, статус или признак владения от
клиента не считается доверенным. Авторизация и business invariants повторно
проверяются на сервере и внутри транзакций Store.

## 2. Данные и классификация

| Класс | Примеры | Правило |
|---|---|---|
| Secret | JWT secret, API keys, bot token | только env/Secret Manager; никогда в git/log/URL |
| Restricted PII | email, имя, телефон, encrypted TOTP seed | private endpoints, no-store, backup encryption |
| Sensitive business | заказы, GMV, refund, pickup code | RBAC + object ownership + audit |
| Public | карточки боксов, адрес точки, approved reviews | redacted response models |

Гостевой `GET /orders/{code}` использует 50-битный CSPRNG bearer-код и отдельную
`PublicOrder`-модель без имени, телефона, внутренних ID и `partner_id`. Сам код
редактируется из access logs.

## 3. Реализованные application controls

### Authentication

- Argon2id: 64 MiB, 3 прохода, parallelism 4, уникальная соль.
- Legacy PBKDF2 проверяется и прозрачно rehash'ится в Argon2id после входа.
- Access JWT HS256: issuer, signature, `alg`, `typ`, expiry и token version.
- Access TTL 15 минут; password change/logout-all отзывает все старые JWT.
- Refresh token хранится только SHA-256 hash'ем, TTL 30 дней.
- Атомарная refresh rotation с token-family reuse detection: повтор старого
  refresh отзывает всё семейство.
- Brute-force controls: IP rate limit + account jail.
- Production fail-fast при слабом JWT key или отсутствии отдельного data key.
- Admin TOTP обязателен: seed зашифрован AES-256-GCM с user-id AAD;
  ±1 time-step, atomic replay counter, hashed one-time recovery codes.
- JWT `amr` и refresh family сохраняют MFA assurance; legacy/non-MFA admin token
  fail-closed отклоняется control plane.
- Email verification/reset используют 256-bit single-use tokens: в SQLite только
  SHA-256 hash, purpose/TTL, reissue invalidation; reset атомарно отзывает sessions.
- Forgot-password всегда возвращает одинаковый `202`, без account enumeration.

### Authorization

- Private API — deny-by-default, env не может отключить RBAC.
- Роли: customer / partner / admin.
- Партнёр имеет неизменяемый tenant `partner_id`; Store хранит
  `owner_user_id`; create/read/redeem проверяют оба значения.
- `/partner/me/*` не принимает tenant ID от клиента.
- Legacy `/partners/{id}/orders` authenticated, deprecated и проходит tenant
  guard.
- Customer orders и reviews проверяются через JWT subject (`WHERE user_id=?`).
- Admin не создаётся публичной регистрацией; только operator CLI.

### Request and API security

- Pydantic allowlist/type/length/range/format validation.
- Timezone-aware pickup windows; истёкшие боксы скрыты и не покупаются.
- JSON-only mutation API (`415` для другого Content-Type).
- Body limit 64 KiB (настраивается 1 KiB–1 MiB), включая chunked body.
- Host allowlist против Host Header Injection.
- Явный CORS origin allowlist, без wildcard credentials.
- Parameterized DB-API queries для PostgreSQL/SQLite; пользовательские строки не конкатенируются в SQL.
- Production schema — только Alembic revisions; startup-DDL оставлен лишь SQLite dev/test.
- Atomic inventory decrement, redeem и refund guards против race/double action.
- Endpoint-local limits для auth/orders/AI + optional Redis distributed guard.
  Redis использует atomic Lua INCR/EXPIRE, keyed pseudonymous identity и fail-closed
  `503`; без `REDIS_URL` single-instance режим сохраняет локальные guards.

### Browser and HTTP

- HSTS, CSP, frame deny, nosniff, referrer и permissions policies.
- COOP, CORP, cross-domain-policy deny, request correlation ID.
- `Cache-Control: no-store` для HTML/API/auth/PII; immutable cache только images.
- Swagger/Redoc отключены; OpenAPI schema доступна только в development.
- Production browser auth — same-origin BFF: access/refresh только в
  `Secure + HttpOnly + SameSite=Strict` cookies; JS получает лишь CSRF token и
  публичный профиль. Double-submit CSRF + Origin check защищают mutations.
- Bearer API сохранён для non-browser clients и не использует cookie-CSRF.

### SDLC

- Unit/integration/security tests, включая BOLA/IDOR, PII redaction, migrations,
  races/invariants и request policies.
- Ruff, Bandit, pip-audit и compile checks в CI.
- Reproducible production/dev lock files.
- Generated Pages build проверяется на reproducibility.
- Container/IaC/secret/CodeQL scanning описаны в CI roadmap ниже.

## 4. STRIDE threat model

| Threat | Main scenario | Existing mitigation | Residual action |
|---|---|---|---|
| Spoofing | украденный пароль/JWT | Argon2id, short JWT, mandatory admin TOTP, rotation/revocation/jail | WebAuthn/passkeys, email verification, login alerts |
| Tampering | partner меняет чужой box/order | tenant ownership, RBAC, parameterized SQL | independent pentest |
| Repudiation | спор по refund/redeem | audit event + request ID + UTC timestamps | append-only external log/SIEM |
| Information disclosure | enumeration/PII leak | redacted models, high-entropy code, no-store | encryption at rest/offsite backups |
| Denial of service | auth hashing/AI/HTTP flood | rate/body limits, bounded inputs | Cloudflare WAF/DDoS + distributed limiter |
| Elevation of privilege | self-register admin/IDOR | operator-only admin, TOTP assurance, deny-by-default, BOLA tests | WebAuthn and admin network policy |

Business abuse отдельно: partner self-registration теперь `pending`; только MFA
admin может approve, а suspension отзывает сессии и inventory. Остаточные риски —
поддельные документы, refund fraud, no-show disputes и compromised cashier. До
денежных операций нужны KYC evidence и payment webhook signatures/idempotency;
refund request ownership/admin workflow уже реализован, но реальный provider refund ещё внешний.

## 5. Честная матрица maximum specification

| Control family | Status | Comment / release gate |
|---|---|---|
| Distributed rate limiting | IMPLEMENTED/PARTIAL | Redis atomic guard готов; managed Redis/edge rollout external |
| DDoS L3/L4/L7, Anycast, CDN | EXTERNAL | Cloudflare plan/config, не код приложения |
| WAF/OWASP CRS/bot/IP reputation | EXTERNAL | Cloudflare managed + custom rules |
| TLS 1.3/PFS/OCSP/HTTP3 | EXTERNAL | Cloudflare/Render evidence required |
| JWT/RBAC/BOLA/validation | IMPLEMENTED | automated negative tests |
| Partner/staff access | IMPLEMENTED | hidden buyer UI, invitation-only owner/manager/cashier, hashed single-use links, server RBAC |
| Production demo isolation | IMPLEMENTED | no seed/fake-paid/static venues/example reviews/demo PIN; provider absent = fail-closed |
| Stripe Checkout payments | IMPLEMENTED/PARTIAL | reservation, idempotent session, signed webhook, event dedupe/reconciliation; live account external |
| Refund workflow | IMPLEMENTED/PARTIAL | owned single request + MFA decision + atomic state; Stripe Refund API external |
| Argon2id/salt | IMPLEMENTED | transparent PBKDF2 migration |
| Refresh rotation/reuse detection | IMPLEMENTED | token family revoke |
| Admin MFA | IMPLEMENTED/PARTIAL | mandatory encrypted TOTP + recovery/replay protection; WebAuthn/passkeys остаются P0 |
| Email verification/password recovery | IMPLEMENTED/PARTIAL | hashed one-time tokens and flows done; Resend credentials/provider external |
| Phone verification | GAP/P1 | нужен SMS provider и abuse controls |
| OAuth2/OIDC | N/A now | добавить только при внешнем IdP; не «для галочки» |
| CSRF | IMPLEMENTED for browser | SameSite Strict + double-submit header + Origin check; Bearer API N/A |
| Strict CSP/no inline/Trusted Types | PARTIAL | executable inline JS/handlers запрещены; inline styles и Trusted Types ещё P1 |
| Secure token storage | IMPLEMENTED | production tokens только HttpOnly cookies; localStorage хранит display marker/preferences |
| SQLi/NoSQLi/LDAP/XXE | IMPLEMENTED/N/A | parameterized SQLite; XML/LDAP/NoSQL не принимаются |
| SSRF | LOW SURFACE | AI URL константный; не добавлять user-controlled fetch |
| File upload controls | N/A | upload endpoints отсутствуют; вводить полным пакетом |
| AES-256 database encryption | **GAP — P0** | encrypted managed disk/SQLCipher + key manager evidence |
| PostgreSQL/Alembic/pool | IMPLEMENTED | bounded pool, query/lock/idle-tx timeouts, DB readiness, admin saturation stats, replica race test |
| Private DB network/RLS | EXTERNAL/P1 | managed private network and least-privilege DB role; RLS if needed |
| Daily/PITR/immutable/offsite backup | **GAP — P0** | managed retention/PITR and restore drill still require provider evidence |
| SIEM/IDS/IPS/24x7 alerts | EXTERNAL | log drain + alert routing + on-call |
| SAST/SCA | IMPLEMENTED | Bandit/Ruff/pip-audit; CodeQL recommended |
| DAST/pentest/bug bounty | EXTERNAL | staging target + written authorization/scope |
| Container/IaC/secret/SBOM scan | CONFIGURED | Trivy + CodeQL + CycloneDX artifact; verify first CI run |
| ASVS Level 3 | NOT CERTIFIED | evidence + independent verification required |

## 6. Cloudflare/edge deployment checklist

До включения real traffic:

1. Proxy only approved hostnames; origin должен принимать трафик только от edge,
   если hosting plan позволяет IP allowlist/private ingress.
2. Managed WAF + OWASP rules в simulate/log mode, затем block после анализа false
   positives. Не считать WAF заменой server-side validation.
3. Rate rules отдельно для `/auth/login`, `/auth/register`, `/auth/refresh`,
   `/orders`, `/redeem`, `/ai/*`; более строгие для auth/AI.
4. Turnstile на register/login после порога риска; secret только в Secret Manager;
   сервер обязан валидировать token и expected hostname/action.
5. Bot management, IP reputation, ASN/geo rules — только по измеренным abuse cases,
   чтобы не блокировать реальные сети Казахстана.
6. TLS mode Full (strict), automatic renewal, HSTS preload — только после проверки
   всех subdomains.
7. Не доверять `X-Forwarded-For` от произвольного клиента; origin должен доверять
   forwarded headers только известному proxy.
8. Logpush WAF/auth/security events в SIEM с alerting и retention policy.

## 7. Release gates для реальных платежей

Блокирующие условия:

- WebAuthn/passkeys для admin поверх реализованного TOTP/recovery;
- production email delivery/DMARC evidence и документальная KYC-проверка approval;
- signed + timestamped payment webhooks, replay protection и idempotency key;
- encrypted persistent DB и encrypted offsite immutable backup;
- проверенная restore drill и incident response tabletop;
- distributed rate limiting + edge WAF/DDoS;
- Trusted Types и отказ от `style-src 'unsafe-inline'` (script policy уже strict);
- central audit/SIEM alerts;
- DAST и независимый pentest по письменному scope;
- privacy/legal review РК и data retention schedule.

Пока эти пункты не закрыты, продукт должен оставаться demo/pilot без обещания
«maximum security» и без хранения реальных платёжных реквизитов.

## 8. Incident response minimum

1. Секрет/JWT compromise: rotate `YUMMY_SECRET_KEY`, принудительно инвалидировать
   все sessions, проверить audit/WAF logs.
2. PII incident: остановить affected flow, сохранить forensic evidence read-only,
   определить scope и выполнить legal notification procedure.
3. Refresh reuse alerts: revoke family автоматически; SIEM должен уведомить user
   и security owner.
4. Backup incident: не перезаписывать последнюю хорошую копию; restore в
   изолированную среду, проверить integrity до переключения.
5. После инцидента: timeline, root cause, corrective actions, regression tests.
