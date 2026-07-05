"""Yummy API — магазин боксов + кабинет партнёра + админка.

Флоу: партнёр публикует бокс → пользователь бронирует и оплачивает (демо) →
получает код выдачи (QR) → партнёр выдаёт по коду. Правила no-show/возврата.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi import Request as HttpRequest
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    if store.count() == (0, 0, 0):
        from .seed import seed
        seed(store)
    yield


app = FastAPI(title="Yummy MVP", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

_LOCAL = {"127.0.0.1", "::1", "testclient", "localhost"}


def local_only(req: HttpRequest) -> None:
    host = req.client.host if req.client else None
    if host not in _LOCAL:
        raise HTTPException(403, "Только локально")


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


@app.post("/orders", response_model=OrderResult, status_code=201, tags=["Store"])
def create_order(payload: OrderCreate) -> OrderResult:
    """Забронировать и оплатить бокс (оплата — демо; в проде Kaspi Pay/QR)."""
    box = store.box(payload.box_id)
    if not box:
        raise HTTPException(404, "Бокс не найден")
    if box.qty_left <= 0:
        raise HTTPException(409, "Боксы закончились")

    order = store.create_order(
        _new("o"), _order_code(), box, payload.user_name.strip(), payload.user_phone.strip()
    )
    if order is None:
        raise HTTPException(409, "Боксы только что закончились")
    return OrderResult(order=order, qr_svg=qr_svg(order.code))


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


@app.post("/boxes", response_model=Box, status_code=201, tags=["Partner"])
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


@app.post("/redeem", tags=["Partner"])
def redeem(payload: RedeemInput) -> dict:
    """Выдать заказ по коду (сотрудник партнёра)."""
    ok, message, order = store.redeem(payload.code)
    return {"ok": ok, "message": message, "order": order.model_dump() if order else None}


# --------------------------------------------------------------------------- #
#  Админка
# --------------------------------------------------------------------------- #
@app.get("/admin/stats", tags=["Admin"])
def admin_stats() -> dict:
    return store.stats()


@app.get("/admin/orders", response_model=list[Order], tags=["Admin"])
def admin_orders() -> list[Order]:
    return store.orders()


@app.post("/admin/refund/{order_id}", tags=["Admin"])
def admin_refund(order_id: str) -> dict:
    return {"refunded": store.refund(order_id)}


@app.post("/admin/seed", tags=["Dev"], dependencies=[Depends(local_only)])
def reseed() -> dict:
    from .seed import seed
    seed(store)
    p, b, o = store.count()
    return {"partners": p, "boxes": b, "orders": o}
