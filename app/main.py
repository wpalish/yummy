"""Yummy API — магазин боксов + кабинет партнёра + админка.

Флоу: партнёр публикует бокс → пользователь бронирует и оплачивает (демо) →
получает код выдачи (QR) → партнёр выдаёт по коду. Правила no-show/возврата.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import time
import secrets
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi import Request as HttpRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi import Response as HttpResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from . import ai as ai_mod
from . import notify as notify_mod
from .accounts import (
    AuthResult,
    InviteAcceptInput,
    InvitePreview,
    PublicUser,
    StaffInvitationCreate,
    StaffInvitationResult,
    StaffRoleUpdate,
    _ENFORCE,
    assert_prod_config,
    current_user,
    optional_user,
    require_role,
)
from .accounts import router as accounts_router
from .auth_telegram import router as telegram_router
from .db import Store
from datetime import datetime, timedelta, timezone

from .models import (
    CATEGORY_RU,
    Box,
    BoxCreate,
    BoxTemplateCreate,
    CommissionRuleInput,
    PaymentAccountInput,
    BoxDescribeInput,
    BoxDescribeResult,
    Order,
    OrderCreate,
    OrderResult,
    Partner,
    RedeemInput,
    BoxUpdate,
    Review,
    ReviewCreate,
    VenueInterest,
    VenueInterestInput,
)
from .qr import qr_svg

store = Store()
_STATIC = Path(__file__).parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("yummy")


def _iph(req: HttpRequest) -> str:
    """IP в аудит — хешем (ПДн по закону РК); корреляция событий сохраняется."""
    from .accounts import ip_hash
    return ip_hash(req.client.host if req and req.client else "?")


class _AuditToDB(logging.Handler):
    """Строки «audit: …» дублируются в БД: stdout Render ротируется,
    журнал безопасности обязан переживать рестарты. Сбой записи не роняет запрос."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if msg.startswith("audit:"):
                from .accounts import accounts as _acc
                _acc.audit_write(msg)
        except Exception:                       # noqa: BLE001
            pass


log.addHandler(_AuditToDB())

# CORS: разрешаем только явные origin'ы из env (для деплоя, когда фронт на Pages,
# а API на другом домене). По умолчанию — localhost. Без wildcard с credentials.
_CORS = [o.strip() for o in os.getenv(
    "YUMMY_CORS_ORIGINS",
    "http://localhost:8021,http://127.0.0.1:8021,https://wpalish.github.io",
).split(",") if o.strip()]

# CSP без 'unsafe-inline' в script-src: фронт переведён на делегирование событий
# (data-act вместо inline onclick), единственный inline <script> подписан per-request
# nonce (см. index()). style-src оставляет 'unsafe-inline' — инлайн-стили безопаснее
# скриптов, а вынос всех style-атрибутов — отдельная работа. CDN для Leaflet.
def _csp(nonce: str | None = None) -> str:
    script_src = "'self' https://unpkg.com https://cdn.jsdelivr.net"
    if nonce:
        script_src += f" 'nonce-{nonce}'"
    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "img-src 'self' data: https:; font-src 'self' data: https://fonts.gstatic.com; "
        "connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
    )


_SEC_HEADERS = {
    "Content-Security-Policy": _csp(),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # изоляция от cross-origin атак (Spectre-класс): окно не шарит browsing
    # context group; ресурсы API читает только своя витрина (CORS уже правит)
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "cross-origin",
    # запретить Adobe cross-domain policy (устаревший, но дешёвый вектор)
    "X-Permitted-Cross-Domain-Policies": "none",
}

# Лимит тела запроса против DoS «большим body». API принимает крошечные JSON —
# 64 KiB с огромным запасом. Настраивается YUMMY_MAX_BODY_BYTES (напр. для будущих
# загрузок). Проверяем Content-Length рано, до чтения тела.
_MAX_BODY = int(os.getenv("YUMMY_MAX_BODY_BYTES", str(64 * 1024)))

# Host allowlist против Host Header Injection. Пусто → "*" (демо/локально не ломаем).
# В проде задать YUMMY_ALLOWED_HOSTS=yummy-astana.onrender.com (через запятую).
_ALLOWED_HOSTS = [h.strip() for h in os.getenv("YUMMY_ALLOWED_HOSTS", "").split(",") if h.strip()] or ["*"]

# --------------------------------------------------------------------------- #
#  Демо vs прод: demo-поведение теперь ЯВНОЕ и выключаемое.
#
#  YUMMY_PAYMENT_MODE:
#    demo (умолчание) — оплата имитируется, QR выдаётся сразу. Так живёт пилот,
#                       в UI это честно подписано.
#    disabled         — платёжного провайдера нет → покупка НЕДОСТУПНА (503),
#                       вместо фейкового «оплачено». Публиковать платный бокс
#                       можно только партнёру с активным мерчант-аккаунтом.
#  (значение kaspi появится вместе с реальной Kaspi-интеграцией)
#
#  YUMMY_DEMO_SEED: посев демо-заведений. В проде (YUMMY_ENFORCE_AUTH=1) НИКОГДА
#  не сеем сам — пустая БД должна давать пустой каталог, а не выдуманные кофейни.
# --------------------------------------------------------------------------- #
_PAYMENT_MODE = os.getenv("YUMMY_PAYMENT_MODE", "demo").strip().lower()
_DEMO_PAY = _PAYMENT_MODE == "demo"
_DEMO_SEED = (os.getenv("YUMMY_DEMO_SEED", "").lower() in {"1", "true", "yes"}
              or not _ENFORCE)


async def _sweeper():
    """Фоновая уборка раз в 10 минут: материализация no-show (expired),
    снятие протухших резервов под оплату, retention аудита. Раньше всё это
    происходило лениво при чтении — строки могли висеть «paid» вечно."""
    import asyncio
    from .accounts import accounts as users_db
    while True:
        try:
            n1 = store.expire_overdue()
            n2 = store.release_expired_pending()
            users_db.audit_sweep()
            if n1 or n2:
                log.info("sweeper: expired=%s released_pending=%s", n1, n2)
        except Exception as exc:                # noqa: BLE001 — свипер не умирает
            log.warning("sweeper error: %s", exc)
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_prod_config()  # fail-fast: прод-режим не стартует с dev-секретом
    # Демо-заведения сеем ТОЛЬКО вне прода: иначе сервис показывал бы людям
    # выдуманные кофейни с реальными адресами как настоящих партнёров.
    if _DEMO_SEED and store.count() == (0, 0, 0):
        from .seed import seed
        seed(store)
    elif not _DEMO_SEED:
        log.info("demo-seed выключен (прод): пустая БД → пустой каталог")
    import asyncio
    task = asyncio.create_task(_sweeper())
    yield
    task.cancel()


# Swagger/Redoc/OpenAPI выключаем в проде (YUMMY_ENFORCE_AUTH=1) — меньше surface
# и не подсказываем структуру API. В демо/деве /docs остаётся для удобства.
_DOCS = None if _ENFORCE else "/docs"
app = FastAPI(
    title="Yummy MVP", version=__version__, lifespan=lifespan,
    docs_url=_DOCS, redoc_url=None,
    openapi_url=None if _ENFORCE else "/openapi.json",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_ALLOWED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],   # правка/снятие боксов
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,          # httpOnly refresh-cookie (origin'ы явные, не "*")
    expose_headers=["X-Request-Id"],
)


@app.middleware("http")
async def security_headers(request: HttpRequest, call_next):
    # correlation ID: сквозная трассировка запроса в логах/ответе (для инцидентов)
    rid = uuid.uuid4().hex
    request.state.request_id = rid

    # лимит тела: отклоняем оверсайз до обработки
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > _MAX_BODY:
        resp = JSONResponse({"detail": "Тело запроса слишком большое"}, status_code=413)
        resp.headers["X-Request-Id"] = rid
        return resp

    try:
        response = await call_next(request)
    except Exception as exc:                     # noqa: BLE001 — необработанный 500
        from . import errmon
        errmon.report(exc, request.url.path)     # Sentry/TG, no-op без конфига
        raise                                    # стандартный 500-ответ остаётся
    for k, v in _SEC_HEADERS.items():
        response.headers.setdefault(k, v)
    response.headers["X-Request-Id"] = rid
    # fingerprint-заголовок Server снимается флагом uvicorn --no-server-header
    # (см. Procfile/render.yaml/Dockerfile) — на уровне middleware его не убрать.
    return response


@app.get("/.well-known/security.txt", include_in_schema=False)
def security_txt() -> PlainTextResponse:
    return PlainTextResponse(
        "Contact: mailto:alisher.nursain@gmail.com\n"
        "Preferred-Languages: ru, en\n"
        "Policy: ответственное раскрытие; без DoS и доступа к чужим данным\n"
    )


app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
app.include_router(telegram_router)
from .telegram_bot import router as tgbot_router  # noqa: E402 (после app)
app.include_router(tgbot_router)
app.include_router(accounts_router)

_LOCAL = {"127.0.0.1", "::1", "testclient", "localhost"}


def local_only(req: HttpRequest) -> None:
    host = req.client.host if req.client else None
    if host not in _LOCAL:
        raise HTTPException(403, "Только локально")


# In-memory rate limit: защита от спама заказами без Redis (для одного инстанса).
_RATE_MAX = 8          # заказов
_RATE_WINDOW = 60.0    # за окно, сек
_rate_hits: dict[str, deque[float]] = {}


def rate_limit_orders(req: HttpRequest) -> None:
    """Не более _RATE_MAX заказов с одного IP за _RATE_WINDOW секунд."""
    from .accounts import _purge_hits
    ip = req.client.host if req.client else "?"
    now = time.monotonic()
    _purge_hits(_rate_hits, _RATE_WINDOW)
    hits = _rate_hits.setdefault(ip, deque())
    while hits and now - hits[0] > _RATE_WINDOW:
        hits.popleft()
    if len(hits) >= _RATE_MAX:
        raise HTTPException(429, "Слишком много заказов подряд, подождите минуту")
    hits.append(now)


# AI-вызовы стоят денег — отдельный, более строгий лимит.
_AI_MAX, _AI_WINDOW = 6, 60.0
_ai_hits: dict[str, deque[float]] = {}


def rate_limit_ai(req: HttpRequest) -> None:
    from .accounts import _purge_hits
    ip = req.client.host if req.client else "?"
    now = time.monotonic()
    _purge_hits(_ai_hits, _AI_WINDOW)
    hits = _ai_hits.setdefault(ip, deque())
    while hits and now - hits[0] > _AI_WINDOW:
        hits.popleft()
    if len(hits) >= _AI_MAX:
        raise HTTPException(429, "Слишком много запросов к AI, подождите минуту")
    hits.append(now)


def _new(prefix: str, n: int = 8) -> str:
    return f"{prefix}{uuid.uuid4().hex[:n]}"


# Алфавит без похожих символов (0/O, 1/I/L, 8/B…) — легко продиктовать на
# кассе, трудно подобрать: 27^6 ≈ 387 млн вместо 16^4 = 65 тыс. у hex-кода.
_CODE_ALPHABET = "23456789ACDEFHJKMNPQRTVWXYZ"


def _order_code() -> str:
    return "YM-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


# --------------------------------------------------------------------------- #
#  Страница / служебное
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    # per-request nonce для единственного inline <script>: позволяет держать CSP
    # без 'unsafe-inline'. Плейсхолдер __CSP_NONCE__ в index.html меняем на живой
    # nonce и дублируем его в заголовок CSP этого ответа (middleware не перезапишет).
    nonce = secrets.token_urlsafe(16)
    html = ((_STATIC / "index.html").read_text(encoding="utf-8")
            .replace("__CSP_NONCE__", nonce)
            .replace("__TG_CHANNEL__", os.getenv("YUMMY_TG_CHANNEL", ""))
            .replace("__PAYMENT_MODE__", _PAYMENT_MODE))
    # no-cache: HTML ревалидируется при каждом заходе — после деплоя браузеры
    # не держат неделю старый инлайн-JS (ассеты-то без хешей в именах)
    return HTMLResponse(html, headers={"Content-Security-Policy": _csp(nonce),
                                       "Cache-Control": "no-cache"})


@app.get("/health", tags=["Dev"])
def health() -> dict:
    p, b, o = store.count()
    return {"status": "ok", "partners": p, "boxes": b, "orders": o,
            "payment_mode": _PAYMENT_MODE, "demo_seed": _DEMO_SEED}


# --------------------------------------------------------------------------- #
#  Магазин (покупатель)
# --------------------------------------------------------------------------- #
@app.get("/districts", tags=["Store"])
def districts() -> list[str]:
    return sorted({p.district for p in store.partners()})


@app.get("/boxes", response_model=list[Box], tags=["Store"])
def list_boxes(district: str | None = None) -> list[Box]:
    return store.boxes_available(district)


@app.get("/boxes/{box_id}", response_model=Box, tags=["Store"])
def get_box(box_id: str) -> Box:
    box = store.box(box_id)
    if not box:
        raise HTTPException(404, "Бокс не найден")
    return box


@app.post("/orders", response_model=OrderResult, status_code=201, tags=["Store"],
          dependencies=[Depends(rate_limit_orders)])
def create_order(payload: OrderCreate, bg: BackgroundTasks,
                 user: PublicUser | None = Depends(optional_user)) -> OrderResult:
    """Забронировать и оплатить бокс (оплата — демо; в проде Kaspi Pay/QR).

    С Bearer-токеном заказ привязывается к аккаунту → виден в GET /me/orders
    с любого устройства; без токена работает как гостевой (по коду).
    """
    box = store.box(payload.box_id)
    if not box:
        raise HTTPException(404, "Бокс не найден")
    if box.qty_left <= 0:
        raise HTTPException(409, "Боксы закончились")
    # Нет платёжного провайдера → покупка недоступна. Раньше заказ молча
    # становился «оплаченным» и выдавал QR бесплатно — фейковая продажа.
    if not _DEMO_PAY and not store.can_sell_paid(box.partner_id):
        raise HTTPException(503, "Оплата пока недоступна — заведение ещё не подключило приём платежей")

    store.release_expired_pending()          # снять протухшие резервы под оплату
    require_payment = store.can_sell_paid(box.partner_id)
    order = store.create_order(
        _new("o"), _order_code(), box, payload.user_name.strip(), payload.user_phone.strip(),
        user_id=user.id if user else None, require_payment=require_payment,
    )
    if order is None:
        raise HTTPException(409, "Боксы только что закончились")
    bg.add_task(notify_mod.notify_new_order, order)   # партнёру/опс-чату, без ключа — no-op
    if order.payment_status == "pending":
        # QR не отдаём до оплаты; в проде здесь ссылка на Kaspi мерчанта партнёра
        return OrderResult(order=order, qr_svg="")
    return OrderResult(order=order, qr_svg=qr_svg(order.code))


@app.post("/orders/confirm-payment", response_model=OrderResult, tags=["Store"],
          dependencies=[Depends(rate_limit_orders),
                        Depends(require_role("admin"))])
def confirm_payment(payload: RedeemInput) -> dict:
    """Подтвердить оплату заказа (pending → paid), выдать QR, начислить комиссию.
    ТОЛЬКО админ: раньше заглушка была открыта — покупатель мог сам перевести
    свой pending-заказ в «оплачен» и получить QR бесплатно. В проде этот переход
    будет делать подписанный Kaspi-webhook, до него — админ вручную."""
    order = store.confirm_payment(payload.code)
    if not order:
        raise HTTPException(409, "Заказ не найден или уже оплачен")
    store.accrue_commission(_new("cl"), order)   # долг партнёра фиксируется при оплате
    return OrderResult(order=order, qr_svg=qr_svg(order.code))


@app.get("/me/orders", response_model=list[Order], tags=["Store"])
def my_orders(user: PublicUser = Depends(current_user)) -> list[Order]:
    """История заказов аккаунта (кросс-девайс, паттерн /me/* из чеклиста)."""
    return store.user_orders(user.id)


@app.get("/me/export", tags=["Store"])
def export_me(user: PublicUser = Depends(current_user)) -> dict:
    """Privacy: скачать все свои данные одним JSON (профиль + заказы)."""
    from .accounts import accounts as users_db
    row = users_db.by_id(user.id)
    profile = {k: row[k] for k in ("id", "email", "role", "brand_name", "address", "created_at")}
    return {"profile": profile,
            "orders": [o.model_dump() for o in store.user_orders(user.id)]}


@app.delete("/me", tags=["Store"])
def delete_me(req: HttpRequest, user: PublicUser = Depends(current_user)) -> dict:
    """Privacy: удалить аккаунт — вход невозможен, PII в заказах обезличен."""
    from .accounts import accounts as users_db
    with users_db._lock, users_db._conn() as c:
        c.execute(
            "UPDATE users SET is_active=0, email=?, pw_hash='',"
            " token_ver=COALESCE(token_ver,0)+1 WHERE id=?",
            (f"deleted-{user.id}", user.id),
        )
    users_db.revoke_all_refresh(user.id)
    scrubbed = store.scrub_user(user.id)
    log.info("audit: delete-account id=%s orders_scrubbed=%s ip=%s",
             user.id, scrubbed, _iph(req))
    return {"status": "deleted", "orders_anonymized": scrubbed}


@app.get("/me/recommendations", response_model=list[Box], tags=["Store"])
def my_recommendations(user: PublicUser = Depends(current_user)) -> list[Box]:
    """Без AI: чаще заказанная категория/заведение весят больше при подборе.
    Нет истории — просто ближайшие по окну выдачи."""
    return store.recommend_boxes(user.id)


@app.get("/orders/{code}", response_model=Order, tags=["Store"])
def order_status(code: str) -> Order:
    order = store.order_by_code(code)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    return order


# --------------------------------------------------------------------------- #
#  Кабинет партнёра
# --------------------------------------------------------------------------- #
@app.get("/partners", response_model=list[Partner], tags=["Partner"])
def list_partners() -> list[Partner]:
    return store.partners()


def _assert_owns(partner_id: str, user: PublicUser | None) -> None:
    """Партнёр работает ТОЛЬКО со своим заведением; админ — с любым.
    Раньше роль проверялась, а владение нет: партнёр мог править чужие боксы."""
    if user is None or user.role == "admin":
        return                       # админ (или демо-режим без ENFORCE)
    if user.partner_id != partner_id:
        raise HTTPException(403, "Это заведение вам не принадлежит")


def _assert_can_edit(user: PublicUser | None) -> None:
    """Кассир только выдаёт заказы; менять витрину — владелец/менеджер."""
    if user is None or user.role == "admin":
        return
    if user.partner_role not in {"owner", "manager"}:
        raise HTTPException(403, "Недостаточно прав: нужен владелец или менеджер")


def _assert_owner(partner_id: str, user: PublicUser | None) -> None:
    """Персонал заведения (нанять/сменить роль/отключить) — только владелец
    своего заведения; админ — любого. Менеджер/кассир персонал не трогают."""
    _assert_owns(partner_id, user)
    if user is None or user.role == "admin":
        return
    if user.partner_role != "owner":
        raise HTTPException(403, "Управлять персоналом может только владелец")


@app.patch("/boxes/{box_id}", response_model=Box, tags=["Partner"])
def update_box(box_id: str, payload: BoxUpdate,
               user: PublicUser | None = Depends(require_role("partner", "admin"))) -> Box:
    """Редактировать бокс: цена, состав, окно выдачи, остаток."""
    owner = store.box_owner(box_id)
    if not owner:
        raise HTTPException(404, "Бокс не найден")
    _assert_owns(owner, user)
    _assert_can_edit(user)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(422, "Нечего менять")
    price = data.get("price")
    value = data.get("value_est")
    cur = store.box(box_id)
    if (value if value is not None else cur.value_est) < (price if price is not None else cur.price):
        raise HTTPException(400, "Ценность содержимого должна быть не ниже цены бокса")
    box = store.update_box(box_id, **data)
    if not box:
        raise HTTPException(404, "Бокс не найден")
    return box


@app.delete("/boxes/{box_id}", tags=["Partner"])
def close_box(box_id: str,
              user: PublicUser | None = Depends(require_role("partner", "admin"))) -> dict:
    """Снять бокс с продажи. Уже оплаченные заказы остаются — их надо выдать."""
    owner = store.box_owner(box_id)
    if not owner:
        raise HTTPException(404, "Бокс не найден")
    _assert_owns(owner, user)
    _assert_can_edit(user)
    if not store.close_box(box_id):
        raise HTTPException(409, "Бокс уже снят с продажи")
    return {"ok": True, "message": "Бокс снят с продажи"}


@app.post("/boxes", response_model=Box, status_code=201, tags=["Partner"])
def create_box(payload: BoxCreate, bg: BackgroundTasks,
               user: PublicUser | None = Depends(require_role("partner", "admin"))) -> Box:
    """Партнёр публикует бокс. Подписчикам Telegram-бота уходит уведомление
    в фоне (best-effort): без TELEGRAM_BOT_TOKEN рассылка тихо пропускается."""
    _assert_owns(payload.partner_id, user)   # нельзя публиковать от чужого имени
    _assert_can_edit(user)
    if payload.value_est < payload.price:
        raise HTTPException(400, "Ценность содержимого должна быть не ниже цены бокса")
    # Нет верифицированного мерчанта → платный бокс публиковать нельзя (иначе
    # продавали бы то, за что невозможно принять деньги).
    if not _DEMO_PAY and not store.can_sell_paid(payload.partner_id):
        raise HTTPException(403, "Сначала подключите и активируйте приём платежей")
    box = store.create_box(_new("b"), payload)
    bg.add_task(notify_mod.broadcast_new_box, store, box)
    return box


@app.post("/ai/describe-box", response_model=BoxDescribeResult, tags=["Partner"],
          dependencies=[Depends(require_role("partner", "admin")), Depends(rate_limit_ai)])
async def describe_box(payload: BoxDescribeInput) -> BoxDescribeResult:
    """Партнёр пишет черновик («остались круассаны») → продающее описание.
    Без ANTHROPIC_API_KEY — деградирует на детерминированный шаблон, не 501:
    это фича с очевидным офлайн-фолбэком, в отличие от Kaspi/Telegram-слотов."""
    category_ru = CATEGORY_RU.get(payload.category, payload.category)
    try:
        text = await ai_mod.generate_box_description(category_ru, payload.notes)
        return BoxDescribeResult(description=text, ai=True)
    except ai_mod.AIUnavailable:
        text = ai_mod.fallback_box_description(category_ru, payload.notes)
        return BoxDescribeResult(description=text, ai=False)


@app.get("/partners/{partner_id}/boxes", response_model=list[Box], tags=["Partner"])
def partner_boxes(partner_id: str) -> list[Box]:
    return store.partner_boxes(partner_id)


# --------------------------------------------------------------------------- #
#  Платежи и комиссия: деньги идут напрямую партнёру (его Kaspi), Yummy ведёт
#  учёт долга по комиссии. РЕАЛЬНЫЙ Kaspi API (подпись/QR/webhook) требует
#  официальных доков Kaspi + мерчант-аккаунта — это отдельный внешний слой.
# --------------------------------------------------------------------------- #
@app.get("/partners/{partner_id}/payment-account", tags=["Partner"])
def get_payment_account(partner_id: str) -> dict:
    a = store.payment_account(partner_id)
    if not a:
        return {"status": "none", "can_sell_paid": False}
    # merchant_reference наружу маскируем (последние 4 символа)
    ref = a.get("merchant_reference") or ""
    return {"status": a["status"], "provider": a["provider"],
            "payments_enabled": bool(a["payments_enabled"]),
            "merchant_masked": ("…" + ref[-4:]) if ref else "",
            "can_sell_paid": store.can_sell_paid(partner_id)}


@app.get("/auth/invite/{token}", response_model=InvitePreview, tags=["Accounts"])
def invite_preview(token: str) -> InvitePreview:
    """Показать, на что инвайт, до ввода пароля. Токен НЕ гасится."""
    from .accounts import accounts as users_db
    row = users_db.peek_invitation(token)
    if not row:
        raise HTTPException(404, "Приглашение недействительно или истекло")
    return InvitePreview(email=row["email"], partner_role=row["partner_role"],
                         brand_name=row["brand_name"] or "")


@app.post("/auth/accept-invite", response_model=AuthResult, status_code=201,
          tags=["Accounts"])
def accept_invite(data: InviteAcceptInput, req: HttpRequest,
                  response: HttpResponse) -> AuthResult:
    """Единственный путь стать партнёром/персоналом — одноразовый инвайт админа."""
    from .accounts import accounts as users_db
    from .accounts import (_public, _row_token_ver, _set_refresh_cookie,
                           create_token, hash_password)
    row = users_db.claim_invitation(data.token)          # атомарно гасит
    if not row:
        raise HTTPException(404, "Приглашение недействительно или истекло")
    if users_db.by_email(row["email"]):
        raise HTTPException(409, "Email уже зарегистрирован")
    partner_id = row["partner_id"]
    if row["partner_role"] == "owner" and not partner_id:
        partner_id = store.create_partner_for_owner(
            name=(row["brand_name"] or "").strip() or row["email"],
            address=(row["address"] or "").strip())
    uid = users_db.create(row["email"], hash_password(data.password), "partner",
                          row["brand_name"] or None, row["address"] or None,
                          partner_id=partner_id, partner_role=row["partner_role"])
    u = users_db.by_id(uid)
    log.info("audit: accept-invite id=%s partner_role=%s partner=%s ip=%s rid=%s",
             uid, row["partner_role"], partner_id,
             _iph(req), getattr(req.state, "request_id", "-"))
    new_refresh = users_db.issue_refresh(uid)
    _set_refresh_cookie(response, new_refresh)
    return AuthResult(access_token=create_token(uid, "partner", ver=_row_token_ver(u)),
                      refresh_token=new_refresh, user=_public(u))


@app.post("/venues/interest", tags=["Store"],
          dependencies=[Depends(rate_limit_orders)])
def add_venue_interest(payload: VenueInterestInput) -> dict:
    """«Хочу боксы отсюда» — спрос на заведение из карты. Персональных данных
    не пишем: только счётчик по заведению (кого подключать в первую очередь)."""
    votes = store.add_venue_interest(payload.venue_id, payload.name.strip(),
                                     payload.address.strip(), payload.district.strip())
    return {"ok": True, "votes": votes}


@app.get("/admin/venue-interest", response_model=list[VenueInterest], tags=["Admin"],
         dependencies=[Depends(require_role("admin"))])
def venue_interest(limit: int = 50) -> list[VenueInterest]:
    """Кого зовут покупатели — очередь на подключение."""
    return [VenueInterest(**r) for r in store.venue_interest_top(min(limit, 200))]


@app.get("/admin/users", tags=["Admin"], dependencies=[Depends(require_role("admin"))])
def list_users(limit: int = 200) -> list[dict]:
    """Пользователи: покупатели, персонал заведений, админы."""
    from .accounts import accounts as users_db
    return [dict(r) for r in users_db.list_users(min(limit, 500))]


@app.post("/admin/users/{user_id}/block", tags=["Admin"])
def block_user(user_id: str, req: HttpRequest, active: bool = False,
               admin: PublicUser | None = Depends(require_role("admin"))) -> dict:
    """Заблокировать/разблокировать аккаунт. Блокировка рвёт все сессии сразу."""
    from .accounts import accounts as users_db
    if admin and admin.id == user_id:
        raise HTTPException(409, "Нельзя заблокировать самого себя")
    if not users_db.set_active(user_id, active):
        raise HTTPException(404, "Пользователь не найден")
    log.info("audit: user-%s id=%s by=%s ip=%s rid=%s",
             "unblock" if active else "block", user_id,
             (admin.id if admin else "demo"), _iph(req),
             getattr(req.state, "request_id", "-"))
    return {"ok": True, "is_active": active}


@app.post("/admin/users/{user_id}/revoke-sessions", tags=["Admin"])
def revoke_user_sessions(user_id: str, req: HttpRequest,
                         admin: PublicUser | None = Depends(require_role("admin"))) -> dict:
    """Разлогинить со всех устройств, не блокируя аккаунт."""
    from .accounts import accounts as users_db
    if not users_db.revoke_sessions(user_id):
        raise HTTPException(404, "Пользователь не найден")
    log.info("audit: revoke-sessions id=%s by=%s ip=%s rid=%s", user_id,
             (admin.id if admin else "demo"), _iph(req),
             getattr(req.state, "request_id", "-"))
    return {"ok": True}


@app.get("/admin/orders.csv", tags=["Admin"], dependencies=[Depends(require_role("admin"))])
def export_orders_csv() -> PlainTextResponse:
    """Выгрузка заказов в CSV (бухгалтерия/сверка)."""
    return PlainTextResponse(_orders_csv(store.orders(limit=1_000_000)),  # выгрузка — полная
                             media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="yummy-orders.csv"'})


@app.get("/partners/{partner_id}/orders.csv", tags=["Partner"])
def export_partner_orders_csv(partner_id: str,
                              user: PublicUser | None = Depends(require_role("partner", "admin"))
                              ) -> PlainTextResponse:
    """Партнёр выгружает свои заказы (журнал выдач) в CSV."""
    _assert_owns(partner_id, user)
    return PlainTextResponse(_orders_csv(store.partner_orders(partner_id, limit=1_000_000)),
                             media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="yummy-orders.csv"'})


@app.get("/partners/{partner_id}/daily-stats", tags=["Partner"])
def partner_daily_stats(partner_id: str, days: int = 30,
                        user: PublicUser | None = Depends(require_role("partner", "admin"))
                        ) -> list[dict]:
    """Заказы/выручка партнёра по дням — для графика в кабинете."""
    _assert_owns(partner_id, user)
    return store.partner_daily_stats(partner_id, days=min(max(days, 1), 90))


# --------------------------------------------------------------------------- #
#  Управление персоналом заведения (владелец — из кабинета партнёра)
# --------------------------------------------------------------------------- #
@app.get("/partners/{partner_id}/staff", tags=["Partner"])
def partner_staff(partner_id: str,
                  user: PublicUser | None = Depends(require_role("partner", "admin"))
                  ) -> list[dict]:
    """Список персонала заведения — видит владелец (или админ)."""
    _assert_owner(partner_id, user)
    from .accounts import accounts as users_db
    return [dict(r) for r in users_db.partner_staff(partner_id)]


@app.post("/partners/{partner_id}/staff-invitations", response_model=StaffInvitationResult,
          status_code=201, tags=["Partner"])
def create_partner_staff_invitation(
        partner_id: str, payload: StaffInvitationCreate, req: HttpRequest,
        user: PublicUser | None = Depends(require_role("partner", "admin"))
        ) -> StaffInvitationResult:
    """Владелец нанимает менеджера/кассира В СВОЁ заведение. Роль owner здесь
    недоступна — нового владельца заводит только админ (/admin/staff-invitations)."""
    _assert_owner(partner_id, user)
    if payload.partner_role not in {"manager", "cashier"}:
        raise HTTPException(422, "Владелец приглашает только менеджера или кассира")
    from .accounts import accounts as users_db
    if users_db.by_email(payload.email):
        raise HTTPException(409, "Email уже зарегистрирован")
    raw = users_db.issue_staff_invitation(
        email=payload.email, partner_id=partner_id, partner_role=payload.partner_role,
        invited_by=(user.id if user else "demo"))
    base = os.getenv("YUMMY_PUBLIC_URL", "https://wpalish.github.io/yummy/").rstrip("/")
    log.info("audit: staff-invite(owner) role=%s partner=%s by=%s ip=%s rid=%s",
             payload.partner_role, partner_id, (user.id if user else "demo"),
             _iph(req), getattr(req.state, "request_id", "-"))
    return StaffInvitationResult(invite_url=f"{base}/?invite={raw}")


@app.patch("/partners/{partner_id}/staff/{uid}", tags=["Partner"])
def update_partner_staff_role(partner_id: str, uid: str, payload: StaffRoleUpdate,
                              req: HttpRequest,
                              user: PublicUser | None = Depends(require_role("partner", "admin"))
                              ) -> dict:
    """Владелец меняет роль сотрудника (менеджер↔кассир) внутри заведения."""
    _assert_owner(partner_id, user)
    if user and uid == user.id:
        raise HTTPException(409, "Нельзя менять собственную роль")
    from .accounts import accounts as users_db
    if not users_db.set_partner_role(uid, partner_id, payload.partner_role):
        raise HTTPException(404, "Сотрудник не найден или роль неизменяема")
    log.info("audit: staff-role partner=%s uid=%s -> %s by=%s rid=%s", partner_id, uid,
             payload.partner_role, (user.id if user else "demo"),
             getattr(req.state, "request_id", "-"))
    return {"id": uid, "partner_role": payload.partner_role}


@app.post("/partners/{partner_id}/staff/{uid}/active", tags=["Partner"])
def set_partner_staff_active(partner_id: str, uid: str, req: HttpRequest,
                             active: bool = False,
                             user: PublicUser | None = Depends(require_role("partner", "admin"))
                             ) -> dict:
    """Отключить/вернуть сотрудника. Отключение рвёт все его сессии (как у админ-блока),
    но действует ТОЛЬКО на персонал своего заведения и не на самого владельца."""
    _assert_owner(partner_id, user)
    if user and uid == user.id:
        raise HTTPException(409, "Нельзя отключить самого себя")
    from .accounts import accounts as users_db
    target = users_db.by_id(uid)
    if not target or target["partner_id"] != partner_id:
        raise HTTPException(404, "Сотрудник не найден в этом заведении")
    if target["partner_role"] == "owner":
        raise HTTPException(403, "Владельца отключить нельзя")
    users_db.set_active(uid, active)
    log.info("audit: staff-active partner=%s uid=%s active=%s by=%s rid=%s", partner_id, uid,
             active, (user.id if user else "demo"), getattr(req.state, "request_id", "-"))
    return {"id": uid, "is_active": active}


def _orders_csv(orders: list) -> str:
    """CSV через stdlib csv — сам экранирует запятые/кавычки в названиях.
    Телефон покупателя НЕ выгружаем: лишние персональные данные в файле."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["code", "status", "payment_status", "partner", "category", "price",
                "pickup_from", "pickup_to", "created_at"])
    for o in orders:
        w.writerow([o.code, o.status, getattr(o, "payment_status", ""), o.partner_name,
                    o.category, o.price, o.pickup_from, o.pickup_to, o.created_at])
    return buf.getvalue()


@app.post("/admin/staff-invitations", response_model=StaffInvitationResult,
          status_code=201, tags=["Admin"])
def create_staff_invitation(payload: StaffInvitationCreate, req: HttpRequest,
                            admin: PublicUser | None = Depends(require_role("admin"))
                            ) -> StaffInvitationResult:
    # admin=None в демо-режиме (YUMMY_ENFORCE_AUTH выкл) — как у остальных admin-роутов
    """Админ выдаёт одноразовую ссылку-приглашение: только по ней можно стать
    партнёром/персоналом. Покупатели этот путь не видят и не могут пройти."""
    from .accounts import accounts as users_db
    if users_db.by_email(payload.email):
        raise HTTPException(409, "Email уже зарегистрирован")
    if payload.partner_role == "owner":
        if not payload.brand_name.strip():
            raise HTTPException(422, "Для владельца укажите название заведения")
    elif not payload.partner_id or not store.partner(payload.partner_id):
        raise HTTPException(404, "Заведение не найдено")
    raw = users_db.issue_staff_invitation(
        email=payload.email, partner_id=payload.partner_id,
        partner_role=payload.partner_role, invited_by=(admin.id if admin else "demo"),
        brand_name=payload.brand_name.strip(), address=payload.address.strip())
    base = os.getenv("YUMMY_PUBLIC_URL", "https://wpalish.github.io/yummy/").rstrip("/")
    log.info("audit: staff-invite role=%s by=%s ip=%s rid=%s", payload.partner_role,
             (admin.id if admin else "demo"), _iph(req),
             getattr(req.state, "request_id", "-"))
    return StaffInvitationResult(invite_url=f"{base}/?invite={raw}")


@app.post("/partners/{partner_id}/payment-account", status_code=201, tags=["Admin"],
          dependencies=[Depends(require_role("admin"))])
def connect_payment_account(partner_id: str, payload: PaymentAccountInput) -> dict:
    store.upsert_payment_account(
        _new("pa"), partner_id, uuid.uuid4().hex, payload.merchant_reference, payload.provider)
    return get_payment_account(partner_id)


@app.post("/partners/{partner_id}/payment-account/activate", tags=["Admin"],
          dependencies=[Depends(require_role("admin"))])
def activate_payment_account(partner_id: str, req: HttpRequest) -> dict:
    """Активировать приём платежей (после проверки мерчанта и тест-платежа).
    До этого партнёр не может публиковать платные боксы."""
    if not store.payment_account(partner_id):
        raise HTTPException(404, "Сначала подключите мерчант-аккаунт")
    store.set_payment_account_status(partner_id, "active", payments_enabled=True)
    log.info("audit: payment-account active partner=%s rid=%s",
             partner_id, getattr(req.state, "request_id", "-"))
    return get_payment_account(partner_id)


@app.get("/admin/payment-accounts", tags=["Admin"],
         dependencies=[Depends(require_role("admin"))])
def list_payment_accounts() -> list[dict]:
    """Все платёжные аккаунты + долг по комиссии. Реквизит только маской."""
    out = []
    for a in store.payment_accounts():
        out.append({**a, **store.commission_summary(a["partner_id"]),
                    "rate_bps": store.active_commission_bps(a["partner_id"])})
    return out


@app.post("/partners/{partner_id}/payment-account/suspend", tags=["Admin"],
          dependencies=[Depends(require_role("admin"))])
def suspend_payment_account(partner_id: str, req: HttpRequest) -> dict:
    """Приостановить приём платежей (долг/нарушение). Публикация платных
    боксов блокируется, пока админ не активирует заново."""
    if not store.payment_account(partner_id):
        raise HTTPException(404, "Платёжный аккаунт не найден")
    store.suspend_payment_account(partner_id)
    log.info("audit: payment-account suspended partner=%s rid=%s",
             partner_id, getattr(req.state, "request_id", "-"))
    return get_payment_account(partner_id)


@app.post("/partners/{partner_id}/payment-account/rotate", tags=["Admin"],
          dependencies=[Depends(require_role("admin"))])
def rotate_payment_account(partner_id: str, req: HttpRequest,
                           payload: PaymentAccountInput | None = None) -> dict:
    """Ротация: новый public_id (webhook-URL); если в теле передан
    merchant_reference — перезаписываем и реквизит (перевыпуск в банке),
    он шифруется актуальным ключом."""
    if not store.rotate_payment_public_id(partner_id):
        raise HTTPException(404, "Платёжный аккаунт не найден")
    if payload and payload.merchant_reference:
        store.rotate_merchant_reference(partner_id, payload.merchant_reference)
    log.info("audit: payment-account rotated partner=%s rid=%s",
             partner_id, getattr(req.state, "request_id", "-"))
    return get_payment_account(partner_id)


@app.post("/partners/{partner_id}/commission-invoice", status_code=201, tags=["Admin"],
          dependencies=[Depends(require_role("admin"))])
def create_commission_invoice(partner_id: str, req: HttpRequest) -> dict:
    """Выставить счёт партнёру за накопленную комиссию (все accrued без счёта)."""
    inv = store.create_commission_invoice(_new("inv"), partner_id)
    if not inv:
        raise HTTPException(409, "Нечего выставлять: нет неоплаченной комиссии")
    log.info("audit: invoice created id=%s partner=%s total=%s rid=%s",
             inv["id"], partner_id, inv["total_minor"], getattr(req.state, "request_id", "-"))
    return inv


@app.get("/admin/commission-invoices", tags=["Admin"],
         dependencies=[Depends(require_role("admin"))])
def list_commission_invoices(partner_id: str | None = None) -> list[dict]:
    return store.commission_invoices(partner_id)


@app.post("/admin/commission-invoices/{iid}/{action}", tags=["Admin"],
          dependencies=[Depends(require_role("admin"))])
def set_invoice_status(iid: str, action: str, req: HttpRequest) -> dict:
    """paid — партнёр оплатил счёт; void — аннулировать (строки вернутся
    в пул и попадут в следующий счёт)."""
    if action not in {"paid", "void"}:
        raise HTTPException(422, "Действие: paid или void")
    inv = store.set_invoice_status(iid, action)
    if not inv:
        raise HTTPException(404, "Счёт не найден или уже закрыт")
    log.info("audit: invoice %s id=%s rid=%s", action, iid,
             getattr(req.state, "request_id", "-"))
    return inv


@app.post("/partners/{partner_id}/commission-rule", status_code=201, tags=["Admin"],
          dependencies=[Depends(require_role("admin"))])
def set_commission_rule(partner_id: str, payload: CommissionRuleInput) -> dict:
    store.set_commission_rate(_new("cr"), partner_id, payload.rate_bps)
    return {"partner_id": partner_id, "rate_bps": payload.rate_bps,
            "rate_percent": payload.rate_bps / 100}


@app.get("/partners/{partner_id}/commission", tags=["Partner"])
def partner_commission(partner_id: str) -> dict:
    return {"rate_bps": store.active_commission_bps(partner_id),
            **store.commission_summary(partner_id)}


# --------------------------------------------------------------------------- #
#  Шаблоны боксов — сохранил один раз, публикуешь одной кнопкой каждый вечер
# --------------------------------------------------------------------------- #
@app.get("/partners/{partner_id}/templates", tags=["Partner"])
def list_templates(partner_id: str) -> list[dict]:
    return store.partner_templates(partner_id)


@app.post("/partners/{partner_id}/templates", status_code=201, tags=["Partner"],
          dependencies=[Depends(require_role("partner", "admin"))])
def create_template(partner_id: str, payload: BoxTemplateCreate) -> dict:
    if payload.value_est < payload.price:
        raise HTTPException(400, "Ценность содержимого должна быть не ниже цены бокса")
    return store.create_template(_new("t"), payload)


@app.delete("/partners/{partner_id}/templates/{tid}", tags=["Partner"],
            dependencies=[Depends(require_role("partner", "admin"))])
def delete_template(partner_id: str, tid: str) -> dict:
    return {"deleted": store.delete_template(tid, partner_id)}


@app.post("/partners/{partner_id}/templates/{tid}/publish", response_model=Box,
          status_code=201, tags=["Partner"],
          dependencies=[Depends(require_role("partner", "admin"))])
def publish_template(partner_id: str, tid: str, bg: BackgroundTasks) -> Box:
    """Опубликовать бокс из шаблона: окно выдачи считается от «сейчас»."""
    t = store.template(tid)
    if not t or t["partner_id"] != partner_id:
        raise HTTPException(404, "Шаблон не найден")
    now = datetime.now(timezone.utc)
    box = store.create_box(_new("b"), BoxCreate(
        partner_id=partner_id, category=t["category"], title=t["title"],
        price=t["price"], value_est=t["value_est"], qty=t["qty"],
        pickup_from=now.isoformat(),
        pickup_to=(now + timedelta(hours=t["hours"])).isoformat(),
        description=t["description"] or "",
    ))
    bg.add_task(notify_mod.broadcast_new_box, store, box)
    return box


@app.get("/partners/{partner_id}/orders", response_model=list[Order], tags=["Partner"])
def partner_orders(partner_id: str, limit: int = 200, offset: int = 0) -> list[Order]:
    return store.partner_orders(partner_id, limit=min(max(limit, 1), 1000),
                                offset=max(offset, 0))


# --------------------------------------------------------------------------- #
#  Отзывы — только по завершённому (issued) заказу, «купил и ввёл код»
# --------------------------------------------------------------------------- #
@app.get("/partners/{partner_id}/reviews", response_model=list[Review], tags=["Store"])
def list_reviews(partner_id: str) -> list[Review]:
    return store.partner_reviews(partner_id)


@app.post("/partners/{partner_id}/reviews", response_model=Review, status_code=201,
          tags=["Store"], dependencies=[Depends(rate_limit_ai)])
async def submit_review(partner_id: str, payload: ReviewCreate,
                        user: PublicUser = Depends(current_user)) -> Review:
    # Order не отдаёт user_id наружу — владение проверяем через user_orders()
    # (та же WHERE user_id=? в БД), а не доверяем ID из тела запроса напрямую.
    mine = {o.id: o for o in store.user_orders(user.id)}
    order = mine.get(payload.order_id)
    if not order or order.partner_id != partner_id:
        raise HTTPException(404, "Заказ не найден или не принадлежит вам")
    if order.status != "issued":
        raise HTTPException(409, "Отзыв можно оставить только после получения заказа")
    if store.has_review(order.id):
        raise HTTPException(409, "Отзыв на этот заказ уже оставлен")
    ok, reason = await ai_mod.moderate_review(payload.text)
    status = "approved" if ok else "rejected"
    if not ok:
        raise HTTPException(422, f"Отзыв не прошёл модерацию: {reason}")
    author = (order.user_name or "Покупатель").strip() or "Покупатель"
    return store.create_review(
        _new("rv"), partner_id, order.id, user.id, author,
        payload.rating, payload.text.strip(), status, reason,
    )


@app.post("/redeem", tags=["Partner"],
          dependencies=[Depends(require_role("partner", "admin"))])
def redeem(payload: RedeemInput) -> dict:
    """Выдать заказ по коду (сотрудник партнёра)."""
    ok, message, order = store.redeem(payload.code)
    return {"ok": ok, "message": message, "order": order.model_dump() if order else None}


# --------------------------------------------------------------------------- #
#  Админка
# --------------------------------------------------------------------------- #
@app.get("/admin/stats", tags=["Admin"], dependencies=[Depends(require_role("admin"))])
def admin_stats() -> dict:
    return store.stats()


@app.get("/admin/orders", response_model=list[Order], tags=["Admin"],
         dependencies=[Depends(require_role("admin"))])
def admin_orders(limit: int = 200, offset: int = 0) -> list[Order]:
    """С пагинацией: на тысячах заказов «отдать всё» таймаутит админку."""
    return store.orders(limit=min(max(limit, 1), 1000), offset=max(offset, 0))


@app.post("/admin/sweep", tags=["Admin"], dependencies=[Depends(require_role("admin"))])
def admin_sweep() -> dict:
    """Ручной запуск уборки (фоновый свипер и так ходит раз в 10 минут)."""
    from .accounts import accounts as users_db
    return {"expired": store.expire_overdue(),
            "released_pending": store.release_expired_pending(),
            "audit_purged": users_db.audit_sweep()}


@app.get("/admin/audit", tags=["Admin"], dependencies=[Depends(require_role("admin"))])
def admin_audit(limit: int = 200, offset: int = 0) -> list[dict]:
    """Персистентный аудит-лог (БД, retention 90 дней, IP — хешем)."""
    from .accounts import accounts as users_db
    users_db.audit_sweep()                      # retention по ходу просмотра
    return [dict(r) for r in users_db.audit_recent(limit, offset)]


# --------------------------------------------------------------------------- #
#  Самообслуживание покупателя по коду заказа (владение = знание кода, как /redeem)
# --------------------------------------------------------------------------- #
@app.post("/orders/cancel", tags=["Store"], dependencies=[Depends(rate_limit_orders)])
def cancel_order(payload: RedeemInput, req: HttpRequest) -> dict:
    """Отменить бронь до начала окна выдачи — бокс возвращается в продажу."""
    ok, message = store.cancel_order(payload.code)
    if ok:
        o = store.order_by_code(payload.code)
        if o:
            store.reverse_commission(o.id)  # заказ отменён — комиссия сторнируется
    log.info("audit: cancel code=%s ok=%s ip=%s rid=%s",
             payload.code, ok, _iph(req),
             getattr(req.state, "request_id", "-"))
    if not ok:
        raise HTTPException(409, message)
    return {"ok": True, "message": message}


@app.post("/orders/refund", tags=["Store"], dependencies=[Depends(rate_limit_orders)])
def refund_order(payload: RedeemInput, req: HttpRequest) -> dict:
    """«Заказ не выдали» — самостоятельный возврат с начала окна выдачи.
    Раньше фронт звал /admin/refund: в проде это 401 для покупателя."""
    ok, message = store.refund_by_code(payload.code)
    if ok:
        o = store.order_by_code(payload.code)
        if o:
            store.reverse_commission(o.id)
    log.info("audit: user-refund code=%s ok=%s ip=%s rid=%s",
             payload.code, ok, _iph(req),
             getattr(req.state, "request_id", "-"))
    if not ok:
        raise HTTPException(409, message)
    return {"ok": True, "message": message}


@app.post("/admin/refund/{order_id}", tags=["Admin"],
          dependencies=[Depends(require_role("admin"))])
def admin_refund(order_id: str, req: HttpRequest,
                 user: PublicUser | None = Depends(optional_user)) -> dict:
    ok = store.refund(order_id)
    if ok:
        store.reverse_commission(order_id)
    log.info("audit: refund order=%s ok=%s by=%s ip=%s rid=%s",
             order_id, ok, user.id if user else "demo",
             _iph(req),
             getattr(req.state, "request_id", "-"))
    return {"refunded": ok}


@app.post("/admin/seed", tags=["Dev"], dependencies=[Depends(local_only)])
def reseed() -> dict:
    from .seed import seed
    seed(store)
    p, b, o = store.count()
    return {"partners": p, "boxes": b, "orders": o}
