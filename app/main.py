"""Yummy API — магазин боксов + кабинет партнёра + админка.

Флоу: партнёр публикует бокс → пользователь бронирует и оплачивает (демо) →
получает код выдачи (QR) → партнёр выдаёт по коду. Правила no-show/возврата.
"""
from __future__ import annotations

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
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from . import ai as ai_mod
from . import notify as notify_mod
from .accounts import (
    PublicUser,
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
    Review,
    ReviewCreate,
)
from .qr import qr_svg

store = Store()
_STATIC = Path(__file__).parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("yummy")

# CORS: разрешаем только явные origin'ы из env (для деплоя, когда фронт на Pages,
# а API на другом домене). По умолчанию — localhost. Без wildcard с credentials.
_CORS = [o.strip() for o in os.getenv(
    "YUMMY_CORS_ORIGINS",
    "http://localhost:8021,http://127.0.0.1:8021,https://wpalish.github.io",
).split(",") if o.strip()]

# CSP допускает inline (в приложении много inline-обработчиков) и CDN, с которых
# грузятся Leaflet/qrcode/html5-qrcode и Swagger UI. Строже сделать нельзя без
# перевода фронта на nonce — это отдельная большая работа.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https:; font-src 'self' data: https://fonts.gstatic.com; "
    "connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
)
_SEC_HEADERS = {
    "Content-Security-Policy": _CSP,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_prod_config()  # fail-fast: прод-режим не стартует с dev-секретом
    if store.count() == (0, 0, 0):
        from .seed import seed
        seed(store)
    yield


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
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
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

    response = await call_next(request)
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
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/health", tags=["Dev"])
def health() -> dict:
    p, b, o = store.count()
    return {"status": "ok", "partners": p, "boxes": b, "orders": o}


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
def create_order(payload: OrderCreate,
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

    store.release_expired_pending()          # снять протухшие резервы под оплату
    require_payment = store.can_sell_paid(box.partner_id)
    order = store.create_order(
        _new("o"), _order_code(), box, payload.user_name.strip(), payload.user_phone.strip(),
        user_id=user.id if user else None, require_payment=require_payment,
    )
    if order is None:
        raise HTTPException(409, "Боксы только что закончились")
    if order.payment_status == "pending":
        # QR не отдаём до оплаты; в проде здесь ссылка на Kaspi мерчанта партнёра
        return OrderResult(order=order, qr_svg="")
    return OrderResult(order=order, qr_svg=qr_svg(order.code))


@app.post("/orders/confirm-payment", response_model=OrderResult, tags=["Store"],
          dependencies=[Depends(rate_limit_orders)])
def confirm_payment(payload: RedeemInput) -> dict:
    """Подтвердить оплату заказа (pending → paid), выдать QR, начислить комиссию.
    В ПРОДЕ этот переход делает ТОЛЬКО подписанный Kaspi-webhook — сейчас сам
    эндпоинт открыт как заглушка для теста, пока нет мерчант-интеграции Kaspi."""
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
             user.id, scrubbed, req.client.host if req.client else "?")
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


@app.post("/boxes", response_model=Box, status_code=201, tags=["Partner"],
          dependencies=[Depends(require_role("partner", "admin"))])
def create_box(payload: BoxCreate, bg: BackgroundTasks) -> Box:
    """Партнёр публикует бокс. Подписчикам Telegram-бота уходит уведомление
    в фоне (best-effort): без TELEGRAM_BOT_TOKEN рассылка тихо пропускается."""
    if payload.value_est < payload.price:
        raise HTTPException(400, "Ценность содержимого должна быть не ниже цены бокса")
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
def partner_orders(partner_id: str) -> list[Order]:
    return store.partner_orders(partner_id)


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
def admin_orders() -> list[Order]:
    return store.orders()


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
             payload.code, ok, req.client.host if req.client else "?",
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
             payload.code, ok, req.client.host if req.client else "?",
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
             req.client.host if req.client else "?",
             getattr(req.state, "request_id", "-"))
    return {"refunded": ok}


@app.post("/admin/seed", tags=["Dev"], dependencies=[Depends(local_only)])
def reseed() -> dict:
    from .seed import seed
    seed(store)
    p, b, o = store.count()
    return {"partners": p, "boxes": b, "orders": o}
