"""Yummy API — магазин боксов + кабинет партнёра + админка.

Флоу: партнёр публикует бокс → пользователь бронирует и оплачивает (демо) →
получает код выдачи (QR) → партнёр выдаёт по коду. Правила no-show/возврата.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi import Request as HttpRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from . import ai as ai_mod
from .accounts import (
    PublicUser,
    _ACCESS_COOKIE,
    _CSRF_COOKIE,
    _REFRESH_COOKIE,
    assert_prod_config,
    current_user,
    optional_user,
    require_role,
)
from .accounts import router as accounts_router
from .auth_telegram import router as telegram_router
from .database import close_all_pools
from .db import Store
from .distributed_limit import limiter as distributed_limiter
from .email_delivery import assert_email_config
from .models import (
    CATEGORY_RU,
    Box,
    ManualEmailVerifyInput,
    BoxCreate,
    BoxDescribeInput,
    BoxDescribeResult,
    CheckoutSessionResult,
    CheckoutStatus,
    Order,
    OrderCreate,
    OrderResult,
    Partner,
    PartnerApplication,
    PartnerStatusUpdate,
    PublicOrder,
    RedeemInput,
    RefundDecision,
    RefundRequest,
    RefundRequestCreate,
    Review,
    ReviewCreate,
    StaffInvitationCreate,
    StaffInvitationResult,
)
from .payments import (
    PaymentUnavailable,
    assert_payment_config,
    gateway as payment_gateway,
    payment_mode,
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
_PRODUCTION = (
    os.getenv("YUMMY_ENV", "").lower() == "production"
    or os.getenv("YUMMY_ENFORCE_AUTH", "").lower() in {"1", "true", "yes"}
)
_ALLOWED_HOSTS = [h.strip() for h in os.getenv(
    "YUMMY_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
).split(",") if h.strip()]
try:
    _MAX_REQUEST_BYTES = min(max(int(os.getenv("YUMMY_MAX_REQUEST_BYTES", "65536")), 1024),
                             1_048_576)
except ValueError:
    _MAX_REQUEST_BYTES = 65_536

# Исполняемый JS только из внешних файлов; inline event attributes запрещены.
# Единственный inline script — статичный JSON-LD с фиксированным SHA-256 hash.
_JSON_LD_HASH = "'sha256-NCY2nlvfh72CFfH+MrdaRIq/GKbQ6lFVHKzGONOrzZE='"
_LEAFLET_HASH = "'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo='"
_CSP = (
    "default-src 'self'; "
    f"script-src 'self' {_JSON_LD_HASH} {_LEAFLET_HASH}; script-src-attr 'none'; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https:; font-src 'self' data: https://fonts.gstatic.com; "
    "connect-src 'self'; worker-src 'self'; form-action 'self'; "
    "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
)
if _PRODUCTION:
    _CSP += "; upgrade-insecure-requests"
_SEC_HEADERS = {
    "Content-Security-Policy": _CSP,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cross-Origin-Opener-Policy": "same-origin",
    # API намеренно доступен Pages-витрине через строгий CORS allowlist.
    "Cross-Origin-Resource-Policy": "cross-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
    "X-DNS-Prefetch-Control": "off",
}


class _RequestTooLarge(Exception):
    pass


class RequestPolicyMiddleware:
    """Fail-closed лимит тела и Content-Type policy, включая chunked body."""

    def __init__(self, app, max_bytes: int = 65_536):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                if int(raw_length) > self.max_bytes:
                    await JSONResponse({"detail": "Тело запроса слишком большое"}, status_code=413)(
                        scope, receive, send
                    )
                    return
            except ValueError:
                await JSONResponse({"detail": "Некорректный Content-Length"}, status_code=400)(
                    scope, receive, send
                )
                return
        method = scope.get("method", "GET").upper()
        has_body = raw_length not in (None, b"0") or b"transfer-encoding" in headers
        if method in {"POST", "PUT", "PATCH"} and has_body:
            content_type = headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
            if content_type != b"application/json" and not content_type.endswith(b"+json"):
                await JSONResponse(
                    {"detail": "Для этого API требуется Content-Type: application/json"},
                    status_code=415,
                )(scope, receive, send)
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestTooLarge:
            await JSONResponse({"detail": "Тело запроса слишком большое"}, status_code=413)(
                scope, receive, send
            )


def _assert_database_config() -> None:
    if _PRODUCTION and not store._database.is_postgres:
        raise RuntimeError("production требует PostgreSQL DATABASE_URL; SQLite только dev/test")


def _assert_edge_config() -> None:
    if not _PRODUCTION:
        return
    configured_hosts = os.getenv("YUMMY_ALLOWED_HOSTS", "")
    if not configured_hosts or "*" in _ALLOWED_HOSTS:
        raise RuntimeError("production требует явный YUMMY_ALLOWED_HOSTS без wildcard")
    if not _CORS or any(origin == "*" or not origin.startswith("https://") for origin in _CORS):
        raise RuntimeError("production требует HTTPS allowlist в YUMMY_CORS_ORIGINS")


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_prod_config()  # fail-fast: прод-режим не стартует с dev-секретом
    assert_email_config()
    assert_payment_config(_PRODUCTION)
    _assert_database_config()
    _assert_edge_config()
    if store.count() == (0, 0, 0):
        from .seed import seed
        seed(store)
    try:
        yield
    finally:
        close_all_pools()


app = FastAPI(
    title="Yummy MVP",
    version=__version__,
    lifespan=lifespan,
    # Swagger/Redoc требуют inline bootstrap scripts; не ослабляем CSP ради UI.
    docs_url=None,
    redoc_url=None,
    openapi_url=None if _PRODUCTION else "/openapi.json",
)
app.add_middleware(RequestPolicyMiddleware, max_bytes=_MAX_REQUEST_BYTES)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_ALLOWED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def distributed_rate_guard(request: HttpRequest, call_next):
    path = request.url.path
    if path.startswith(("/auth/", "/session/")):
        bucket, limit, window = "auth", 30, 60
    elif path == "/orders":
        bucket, limit, window = "orders", 20, 60
    elif path == "/redeem":
        bucket, limit, window = "redeem", 60, 60
    elif path == "/webhooks/stripe":
        bucket, limit, window = "stripe-webhook", 1000, 60
    else:
        bucket, limit, window = "general", 300, 60
    identity = request.client.host if request.client else "unknown"
    try:
        allowed, retry_after = distributed_limiter.check(bucket, identity, limit, window)
    except RuntimeError:
        log.exception("distributed limiter unavailable bucket=%s", bucket)
        return JSONResponse(
            {"detail": "Сервис временно недоступен"}, status_code=503,
            headers={"Retry-After": "5"},
        )
    if not allowed:
        return JSONResponse(
            {"detail": "Слишком много запросов"}, status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
    response = await call_next(request)
    if distributed_limiter.configured:
        response.headers["X-RateLimit-Policy"] = f"{limit};w={window}"
    return response


@app.middleware("http")
async def csrf_guard(request: HttpRequest, call_next):
    """Double-submit CSRF для cookie session; Bearer API остаётся CSRF-independent."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        authorization = request.headers.get("authorization", "")
        uses_bearer = authorization.lower().startswith("bearer ")
        uses_cookie = bool(
            request.cookies.get(_ACCESS_COOKIE) or request.cookies.get(_REFRESH_COOKIE)
        )
        if uses_cookie and not uses_bearer:
            cookie_token = request.cookies.get(_CSRF_COOKIE, "")
            header_token = request.headers.get("x-csrf-token", "")
            if (not cookie_token or not header_token
                    or not hmac.compare_digest(cookie_token, header_token)):
                return JSONResponse({"detail": "CSRF-проверка не пройдена"}, status_code=403)
            # Дополнительная browser-boundary проверка; CSRF token остаётся
            # основной защитой для non-browser клиентов без Origin.
            origin = request.headers.get("origin")
            if origin:
                proto = request.headers.get("x-forwarded-proto", request.url.scheme)
                expected = f"{proto}://{request.headers.get('host', '')}"
                if origin.rstrip("/") != expected.rstrip("/"):
                    return JSONResponse({"detail": "Недопустимый Origin"}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: HttpRequest, call_next):
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.monotonic()
    raw_path = request.url.path
    audit_path = "/orders/{code}" if raw_path.startswith("/orders/") else raw_path
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request ERROR id=%s method=%s path=%s", request_id,
                      request.method, audit_path)
        raise
    for k, v in _SEC_HEADERS.items():
        response.headers.setdefault(k, v)
    response.headers["X-Request-ID"] = request_id
    if request.url.path.startswith("/static/img/"):
        response.headers.setdefault("Cache-Control", "public, max-age=604800, immutable")
    else:
        # Auth/PII/API ответы не должны оставаться в shared/browser caches.
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Pragma", "no-cache")
    log.info("request id=%s method=%s path=%s status=%s duration_ms=%s",
             request_id, request.method, audit_path, response.status_code,
             round((time.monotonic() - started) * 1000))
    # fingerprint-заголовок Server снимается флагом uvicorn --no-server-header
    # (см. Procfile/render.yaml/Dockerfile) — на уровне middleware его не убрать.
    return response


@app.get("/.well-known/security.txt", include_in_schema=False)
def security_txt() -> PlainTextResponse:
    return PlainTextResponse(
        "Contact: mailto:alisher.nursain@gmail.com\n"
        "Expires: 2027-07-14T00:00:00Z\n"
        "Preferred-Languages: ru, en\n"
        "Policy: ответственное раскрытие; без DoS и доступа к чужим данным\n"
    )


@app.get("/manifest.json", include_in_schema=False)
def web_manifest() -> FileResponse:
    return FileResponse(_STATIC / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    return FileResponse(
        _STATIC / "sw.js", media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
app.include_router(telegram_router)
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


_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # без 0/O/1/I


def _order_code() -> str:
    """50 бит энтропии, но код остаётся удобным для ручного ввода: YM-XXXXX-XXXXX."""
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(10))
    return f"YM-{raw[:5]}-{raw[5:]}"


def _partner_for_user(user: PublicUser, *, require_approved: bool = True) -> Partner:
    """Вернуть tenant партнёра, не публикуя pending/rejected профиль в Store."""
    if user.role != "partner" or not user.partner_id:
        raise HTTPException(403, "Аккаунт не привязан к заведению")
    if require_approved and user.partner_status != "approved":
        raise HTTPException(403, f"Заведение не одобрено: {user.partner_status or 'pending'}")
    partner = store.partner(user.partner_id)
    if partner:
        if user.partner_role == "owner" and not store.partner_owned_by(partner.id, user.id):
            raise HTTPException(403, "Заведение принадлежит другому аккаунту")
        if user.partner_role not in {"owner", "manager", "cashier"}:
            raise HTTPException(403, "Нет роли персонала")
        return partner
    partner = Partner(
        id=user.partner_id,
        name=(user.brand_name or "Новое заведение").strip(),
        district=(user.district or "Астана").strip(),
        address=(user.address or "Адрес не указан").strip(),
    )
    if user.partner_status != "approved":
        return partner
    store.upsert_partner(partner, owner_user_id=user.id)
    if not store.partner_owned_by(partner.id, user.id):
        raise HTTPException(409, "Не удалось привязать профиль заведения")
    return store.partner(partner.id) or partner


def _authorized_partner_id(user: PublicUser, requested_id: str | None = None) -> str:
    """Tenant guard для private partner API; admin может указать любую точку."""
    if user.role == "admin":
        if not requested_id or not store.partner(requested_id):
            raise HTTPException(404, "Заведение не найдено")
        return requested_id
    partner = _partner_for_user(user)
    if requested_id is not None and requested_id != partner.id:
        raise HTTPException(403, "Нет доступа к чужому заведению")
    return partner.id


def require_approved_partner(
    user: PublicUser = Depends(require_role("partner", "admin")),
) -> PublicUser:
    if user.role == "partner":
        _partner_for_user(user)
        if user.partner_role not in {"owner", "manager"}:
            raise HTTPException(403, "Недостаточно прав персонала")
    return user


# --------------------------------------------------------------------------- #
#  Страница / служебное
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/live", tags=["Dev"])
def liveness() -> dict:
    """Process liveness only; does not consume a DB connection."""
    return {"status": "alive"}


@app.get("/health", tags=["Dev"])
def health() -> dict:
    """Readiness: fails if PostgreSQL/pool checkout/query is unavailable."""
    try:
        store.ping()
    except Exception as exc:
        log.error("readiness database unavailable: %s", type(exc).__name__)
        raise HTTPException(503, "database unavailable") from exc
    if _PRODUCTION:
        return {"status": "ok"}
    p, b, o = store.count()
    return {"status": "ok", "partners": p, "boxes": b, "orders": o}


@app.get("/config", include_in_schema=False)
def public_config() -> dict:
    return {"payment_mode": payment_mode(), "currency": os.getenv("STRIPE_CURRENCY", "kzt")}


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
def create_order(payload: OrderCreate, req: HttpRequest,
                 user: PublicUser | None = Depends(optional_user)) -> OrderResult:
    """Забронировать и оплатить бокс (оплата — демо; в проде Kaspi Pay/QR).

    С Bearer-токеном заказ привязывается к аккаунту → виден в GET /me/orders
    с любого устройства; без токена работает как гостевой (по коду).
    """
    box = store.box(payload.box_id)
    state = store.box_orderability(payload.box_id)
    if not box or state == "missing":
        raise HTTPException(404, "Бокс не найден")
    if state == "sold_out":
        raise HTTPException(409, "Боксы закончились")
    if state == "expired":
        raise HTTPException(409, "Окно выдачи этого бокса уже завершилось")

    order = store.create_order(
        _new("o"), _order_code(), box, payload.user_name.strip(), payload.user_phone.strip(),
        user_id=user.id if user else None,
    )
    if order is None:
        raise HTTPException(409, "Боксы только что закончились")
    log.info("audit: order-create id=%s partner=%s actor=%s ip=%s",
             order.id, order.partner_id, user.id if user else "guest",
             req.client.host if req.client else "?")
    return OrderResult(order=order, qr_svg=qr_svg(order.code))


@app.post("/checkout/sessions", response_model=CheckoutSessionResult, status_code=201,
          tags=["Payments"], dependencies=[Depends(rate_limit_orders)])
def create_checkout_session(
    payload: OrderCreate,
    req: HttpRequest,
    user: PublicUser | None = Depends(optional_user),
) -> CheckoutSessionResult:
    box = store.box(payload.box_id)
    if not box or store.box_orderability(payload.box_id) != "available":
        raise HTTPException(409, "Бокс недоступен")
    payment_id, order_id = _new("pay", 12), _new("o")
    reserved = store.create_checkout_reservation(
        payment_id, order_id, _order_code(), box, payload.user_name.strip(),
        payload.user_phone.strip(), user.id if user else None,
        os.getenv("STRIPE_CURRENCY", "kzt").lower(),
    )
    if not reserved:
        raise HTTPException(409, "Бокс только что закончился")
    order, payment = reserved
    try:
        checkout = payment_gateway.create_checkout(
            payment_id=payment.id, order_id=order.id,
            title=box.title or box.partner_name, amount_minor=payment.amount_minor,
            currency=payment.currency, idempotency_key=payment.idempotency_key,
        )
        if not store.attach_checkout_session(payment.id, checkout["id"]):
            raise PaymentUnavailable("Не удалось привязать Checkout Session")
    except PaymentUnavailable as exc:
        store.fail_checkout_reservation(payment.id)
        raise HTTPException(503, "Платёжный сервис временно недоступен") from exc
    log.info("audit: checkout-created payment=%s order=%s actor=%s ip=%s",
             payment.id, order.id, user.id if user else "guest",
             req.client.host if req.client else "?")
    return CheckoutSessionResult(
        order_id=order.id, payment_id=payment.id, checkout_url=checkout["url"],
        reservation_expires_at=payment.reservation_expires_at,
    )


@app.get("/checkout/sessions/{session_id}", response_model=CheckoutStatus, tags=["Payments"])
def checkout_session_status(session_id: str) -> CheckoutStatus:
    result = store.checkout_status(session_id)
    if not result:
        raise HTTPException(404, "Checkout Session не найдена")
    payment, order = result
    paid = payment.status == "paid" and order.status in {"paid", "issued"}
    public = PublicOrder.from_order(order) if paid else None
    return CheckoutStatus(
        order_id=order.id, payment_status=payment.status,
        order=public, qr_svg=qr_svg(order.code) if paid else None,
    )


@app.post("/webhooks/stripe", tags=["Payments"], include_in_schema=False)
async def stripe_webhook(request: HttpRequest) -> dict:
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = payment_gateway.construct_event(payload, signature)
    except PaymentUnavailable as exc:
        raise HTTPException(400, "Invalid Stripe webhook") from exc
    result = store.process_stripe_event(event, hashlib.sha256(payload).hexdigest())
    return {"received": True, "result": result}


@app.get("/me/orders", response_model=list[Order], tags=["Store"])
def my_orders(user: PublicUser = Depends(current_user)) -> list[Order]:
    """История заказов аккаунта (кросс-девайс, паттерн /me/* из чеклиста)."""
    return store.user_orders(user.id)


@app.post("/me/orders/{order_id}/refund-requests", response_model=RefundRequest,
          status_code=201, tags=["Store"])
def create_my_refund_request(
    order_id: str,
    payload: RefundRequestCreate,
    req: HttpRequest,
    user: PublicUser = Depends(current_user),
) -> RefundRequest:
    refund = store.create_refund_request(
        _new("rr"), order_id, user.id, payload.reason, payload.details.strip()
    )
    if not refund:
        raise HTTPException(409, "Заявка невозможна, уже существует или заказ не подходит")
    log.info("audit: refund-request id=%s order=%s actor=%s ip=%s",
             refund.id, order_id, user.id, req.client.host if req.client else "?")
    return refund


@app.get("/me/refund-requests", response_model=list[RefundRequest], tags=["Store"])
def my_refund_requests(user: PublicUser = Depends(current_user)) -> list[RefundRequest]:
    return store.user_refund_requests(user.id)


@app.get("/me/export", tags=["Store"])
def export_me(user: PublicUser = Depends(current_user)) -> dict:
    """Privacy: скачать все свои данные одним JSON (профиль + заказы)."""
    from .accounts import accounts as users_db
    row = users_db.by_id(user.id)
    profile = {k: row[k] for k in (
        "id", "email", "role", "brand_name", "address", "district", "created_at",
        "terms_accepted_at", "terms_version",
    )}
    return {
        "profile": profile,
        "orders": [o.model_dump() for o in store.user_orders(user.id)],
        "refund_requests": [r.model_dump() for r in store.user_refund_requests(user.id)],
    }


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


@app.get("/orders/{code}", response_model=PublicOrder, tags=["Store"])
def order_status(code: str) -> PublicOrder:
    """Гостевая проверка по высокоэнтропийному коду — без PII и internal id."""
    order = store.order_by_code(code)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    return PublicOrder.from_order(order)


# --------------------------------------------------------------------------- #
#  Кабинет партнёра
# --------------------------------------------------------------------------- #
@app.get("/partners", response_model=list[Partner], tags=["Partner"])
def list_partners() -> list[Partner]:
    return store.partners()


@app.post("/boxes", response_model=Box, status_code=201, tags=["Partner"])
def create_box(
    payload: BoxCreate,
    req: HttpRequest,
    user: PublicUser = Depends(require_role("partner", "admin")),
) -> Box:
    """Партнёр публикует бокс только в своём tenant; admin — в указанном."""
    if user.role == "partner" and user.partner_role not in {"owner", "manager"}:
        raise HTTPException(403, "Только владелец или менеджер публикует боксы")
    partner_id = _authorized_partner_id(user, payload.partner_id)
    if payload.value_est < payload.price:
        raise HTTPException(400, "Ценность содержимого должна быть не ниже цены бокса")
    box = store.create_box(_new("b"), payload.model_copy(update={"partner_id": partner_id}))
    log.info("audit: box-create id=%s partner=%s actor=%s ip=%s",
             box.id, partner_id, user.id, req.client.host if req.client else "?")
    return box


@app.post("/ai/describe-box", response_model=BoxDescribeResult, tags=["Partner"],
          dependencies=[Depends(require_approved_partner), Depends(rate_limit_ai)])
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
    """Публичные карточки точки; PII здесь нет."""
    return store.partner_boxes(partner_id)


@app.get("/partner/me", response_model=Partner, tags=["Partner"])
def my_partner_profile(
    user: PublicUser = Depends(require_role("partner")),
) -> Partner:
    return _partner_for_user(user, require_approved=False)


@app.get("/partner/me/boxes", response_model=list[Box], tags=["Partner"])
def my_partner_boxes(
    user: PublicUser = Depends(require_role("partner")),
) -> list[Box]:
    return store.partner_boxes(_partner_for_user(user).id)


@app.get("/partner/me/orders", response_model=list[Order], tags=["Partner"])
def my_partner_orders(
    user: PublicUser = Depends(require_role("partner")),
) -> list[Order]:
    return store.partner_orders(_partner_for_user(user).id)


@app.get("/partners/{partner_id}/orders", response_model=list[Order], tags=["Partner"],
         deprecated=True)
def partner_orders(
    partner_id: str,
    user: PublicUser = Depends(require_role("partner", "admin")),
) -> list[Order]:
    """Совместимый private endpoint с обязательным tenant guard."""
    return store.partner_orders(_authorized_partner_id(user, partner_id))


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


@app.post("/redeem", tags=["Partner"])
def redeem(
    payload: RedeemInput,
    req: HttpRequest,
    user: PublicUser = Depends(require_role("partner", "admin")),
) -> dict:
    """Выдать заказ: партнёр — только свой, admin — любой."""
    partner_id = None if user.role == "admin" else _partner_for_user(user).id
    ok, message, order = store.redeem(payload.code, partner_id=partner_id)
    log.info("audit: redeem ok=%s order=%s partner=%s actor=%s ip=%s",
             ok, order.id if order else "not-found", partner_id or "admin-any",
             user.id, req.client.host if req.client else "?")
    return {"ok": ok, "message": message, "order": order.model_dump() if order else None}


# --------------------------------------------------------------------------- #
#  Админка
# --------------------------------------------------------------------------- #
@app.post("/admin/staff-invitations", response_model=StaffInvitationResult,
          status_code=201, tags=["Admin"])
def admin_create_staff_invitation(
    payload: StaffInvitationCreate,
    req: HttpRequest,
    admin: PublicUser = Depends(require_role("admin")),
) -> StaffInvitationResult:
    from .accounts import accounts as users_db
    if users_db.by_email(payload.email):
        raise HTTPException(409, "Email уже зарегистрирован")
    if payload.partner_role == "owner":
        if payload.partner_id or not payload.brand_name.strip() or not payload.address.strip():
            raise HTTPException(422, "Для владельца укажите новое заведение и адрес")
    elif not payload.partner_id or not store.partner(payload.partner_id):
        raise HTTPException(404, "Заведение не найдено")
    raw = users_db.issue_staff_invitation(
        email=payload.email, partner_id=payload.partner_id,
        partner_role=payload.partner_role, invited_by=admin.id,
        brand_name=payload.brand_name.strip(), address=payload.address.strip(),
        district=payload.district.strip(),
    )
    url = f"{os.getenv('YUMMY_PUBLIC_URL', '').rstrip('/')}/?invite={raw}"
    log.warning("audit: staff-invite role=%s actor=%s ip=%s",
                payload.partner_role, admin.id, req.client.host if req.client else "?")
    return StaffInvitationResult(invite_url=url)


@app.get("/admin/partner-applications", response_model=list[PartnerApplication], tags=["Admin"])
def admin_partner_applications(
    status: str | None = None,
    user: PublicUser = Depends(require_role("admin")),
) -> list[PartnerApplication]:
    del user  # dependency documents and enforces admin MFA
    from .accounts import accounts as users_db
    if status and status not in {"pending", "approved", "suspended", "rejected"}:
        raise HTTPException(422, "Неизвестный partner status")
    return [PartnerApplication(
        user_id=row["id"], email=row["email"], email_verified=bool(row["email_verified"]),
        brand_name=row["brand_name"] or "",
        address=row["address"] or "", district=row["district"] or "",
        status=row["partner_status"], created_at=row["created_at"],
    ) for row in users_db.partner_accounts(status)]


@app.post("/admin/users/{user_id}/verify-email", tags=["Admin"])
def admin_verify_email_manually(
    user_id: str,
    payload: ManualEmailVerifyInput,
    req: HttpRequest,
    admin: PublicUser = Depends(require_role("admin")),
) -> dict:
    from .accounts import accounts as users_db
    try:
        users_db.mark_email_verified(user_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    reason = payload.reason.replace("\r", " ").replace("\n", " ")[:120]
    log.warning("audit: email-manual-verify user=%s actor=%s reason=%s ip=%s",
                user_id, admin.id, reason, req.client.host if req.client else "?")
    return {"status": "verified", "user_id": user_id}


@app.post("/admin/partners/{user_id}/status", response_model=PartnerApplication, tags=["Admin"])
def admin_set_partner_status(
    user_id: str,
    payload: PartnerStatusUpdate,
    req: HttpRequest,
    admin: PublicUser = Depends(require_role("admin")),
) -> PartnerApplication:
    from .accounts import _public, accounts as users_db
    target = users_db.by_id(user_id)
    if payload.status == "approved" and target and not target["email_verified"]:
        raise HTTPException(409, "Сначала подтвердите email заведения")
    try:
        row = users_db.set_partner_status(user_id, payload.status)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    public = _public(row)
    if payload.status == "approved":
        _partner_for_user(public)
    elif payload.status != "approved" and public.partner_id:
        store.suspend_partner(public.partner_id)
    safe_reason = payload.reason.replace("\r", " ").replace("\n", " ")[:120]
    log.info("audit: partner-status user=%s status=%s actor=%s reason=%s ip=%s",
             user_id, payload.status, admin.id, safe_reason or "-",
             req.client.host if req.client else "?")
    return PartnerApplication(
        user_id=row["id"], email=row["email"], email_verified=bool(row["email_verified"]),
        brand_name=row["brand_name"] or "",
        address=row["address"] or "", district=row["district"] or "",
        status=row["partner_status"], created_at=row["created_at"],
    )


@app.get("/admin/system/database", tags=["Admin"])
def admin_database_status(
    user: PublicUser = Depends(require_role("admin")),
) -> dict:
    del user
    stats = store._database.pool_stats()
    allowed = {
        "pool_min", "pool_max", "pool_size", "pool_available",
        "requests_waiting", "requests_num", "requests_queued",
        "usage_ms", "requests_wait_ms", "connections_num",
        "connections_errors", "connections_lost",
    }
    return {
        "backend": "postgresql" if store._database.is_postgres else "sqlite",
        "ready": store.ping(),
        "pool": {key: value for key, value in stats.items() if key in allowed},
    }


@app.get("/admin/stats", tags=["Admin"], dependencies=[Depends(require_role("admin"))])
def admin_stats() -> dict:
    return store.stats()


@app.get("/admin/orders", response_model=list[Order], tags=["Admin"],
         dependencies=[Depends(require_role("admin"))])
def admin_orders() -> list[Order]:
    return store.orders()


@app.get("/admin/refund-requests", response_model=list[RefundRequest], tags=["Admin"])
def admin_refund_requests(
    status: str | None = None,
    user: PublicUser = Depends(require_role("admin")),
) -> list[RefundRequest]:
    del user
    if status and status not in {"pending", "reviewing", "rejected", "refunded"}:
        raise HTTPException(422, "Неизвестный refund status")
    return store.refund_requests(status)


@app.post("/admin/refund-requests/{request_id}/decision", response_model=RefundRequest,
          tags=["Admin"])
def admin_decide_refund(
    request_id: str,
    payload: RefundDecision,
    req: HttpRequest,
    admin: PublicUser = Depends(require_role("admin")),
) -> RefundRequest:
    resolved = store.resolve_refund_request(
        request_id, payload.action, payload.resolution.strip(), admin.id
    )
    if not resolved:
        raise HTTPException(409, "Заявка уже решена или возврат невозможен")
    safe_resolution = payload.resolution.replace("\r", " ").replace("\n", " ")[:120]
    log.warning("audit: refund-decision id=%s action=%s actor=%s resolution=%s ip=%s",
                request_id, payload.action, admin.id, safe_resolution,
                req.client.host if req.client else "?")
    return resolved


@app.post("/admin/refund/{order_id}", tags=["Admin"], deprecated=True)
def admin_refund(
    order_id: str,
    req: HttpRequest,
    user: PublicUser = Depends(require_role("admin")),
) -> dict:
    ok = store.refund(order_id)
    log.info("audit: refund order=%s ok=%s by=%s ip=%s",
             order_id, ok, user.id,
             req.client.host if req.client else "?")
    return {"refunded": ok}


@app.post("/admin/seed", tags=["Dev"], dependencies=[Depends(local_only)])
def reseed() -> dict:
    from .seed import seed
    seed(store)
    p, b, o = store.count()
    return {"partners": p, "boxes": b, "orders": o}
