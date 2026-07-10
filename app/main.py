"""Yummy API — магазин боксов + кабинет партнёра + админка.

Флоу: партнёр публикует бокс → пользователь бронирует и оплачивает (демо) →
получает код выдачи (QR) → партнёр выдаёт по коду. Правила no-show/возврата.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi import Request as HttpRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .accounts import PublicUser, current_user, optional_user, require_role
from .accounts import router as accounts_router
from .auth_telegram import router as telegram_router
from .db import Store
from .models import (
    Box,
    BoxCreate,
    Order,
    OrderCreate,
    OrderResult,
    Partner,
    RedeemInput,
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
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if store.count() == (0, 0, 0):
        from .seed import seed
        seed(store)
    yield


app = FastAPI(title="Yummy MVP", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: HttpRequest, call_next):
    response = await call_next(request)
    for k, v in _SEC_HEADERS.items():
        response.headers.setdefault(k, v)
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
    ip = req.client.host if req.client else "?"
    now = time.monotonic()
    hits = _rate_hits.setdefault(ip, deque())
    while hits and now - hits[0] > _RATE_WINDOW:
        hits.popleft()
    if len(hits) >= _RATE_MAX:
        raise HTTPException(429, "Слишком много заказов подряд, подождите минуту")
    hits.append(now)


def _new(prefix: str, n: int = 8) -> str:
    return f"{prefix}{uuid.uuid4().hex[:n]}"


def _order_code() -> str:
    return "YM-" + uuid.uuid4().hex[:4].upper()


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

    order = store.create_order(
        _new("o"), _order_code(), box, payload.user_name.strip(), payload.user_phone.strip(),
        user_id=user.id if user else None,
    )
    if order is None:
        raise HTTPException(409, "Боксы только что закончились")
    return OrderResult(order=order, qr_svg=qr_svg(order.code))


@app.get("/me/orders", response_model=list[Order], tags=["Store"])
def my_orders(user: PublicUser = Depends(current_user)) -> list[Order]:
    """История заказов аккаунта (кросс-девайс, паттерн /me/* из чеклиста)."""
    return store.user_orders(user.id)


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
def create_box(payload: BoxCreate) -> Box:
    """Партнёр публикует бокс."""
    if payload.value_est < payload.price:
        raise HTTPException(400, "Ценность содержимого должна быть не ниже цены бокса")
    return store.create_box(_new("b"), payload)


@app.get("/partners/{partner_id}/boxes", response_model=list[Box], tags=["Partner"])
def partner_boxes(partner_id: str) -> list[Box]:
    return store.partner_boxes(partner_id)


@app.get("/partners/{partner_id}/orders", response_model=list[Order], tags=["Partner"])
def partner_orders(partner_id: str) -> list[Order]:
    return store.partner_orders(partner_id)


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


@app.post("/admin/refund/{order_id}", tags=["Admin"],
          dependencies=[Depends(require_role("admin"))])
def admin_refund(order_id: str) -> dict:
    return {"refunded": store.refund(order_id)}


@app.post("/admin/seed", tags=["Dev"], dependencies=[Depends(local_only)])
def reseed() -> dict:
    from .seed import seed
    seed(store)
    p, b, o = store.count()
    return {"partners": p, "boxes": b, "orders": o}
