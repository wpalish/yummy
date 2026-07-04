"""Pydantic-схемы API: партнёры, боксы, заказы."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, computed_field

# Категории боксов из ТЗ
BoxCategory = Literal["sweet", "bakery", "mixed", "snack"]
OrderStatus = Literal["paid", "issued", "expired", "refunded", "cancelled"]

CATEGORY_RU = {
    "sweet": "Sweet Box",
    "bakery": "Bakery Box",
    "mixed": "Mixed Box",
    "snack": "Snack Box",
}
CATEGORY_EMOJI = {"sweet": "🍩", "bakery": "🥐", "mixed": "🧺", "snack": "🥪"}
_DEFAULT_EMOJI = "🧺"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CategoryLabeled(BaseModel):
    """Общие лейблы категории (RU-название и эмодзи) для боксов и заказов."""

    category: BoxCategory

    @computed_field
    @property
    def category_ru(self) -> str:
        return CATEGORY_RU.get(self.category, self.category)

    @computed_field
    @property
    def emoji(self) -> str:
        return CATEGORY_EMOJI.get(self.category, _DEFAULT_EMOJI)


# --------------------------------------------------------------------------- #
#  Партнёры
# --------------------------------------------------------------------------- #
class Partner(BaseModel):
    id: str
    name: str
    district: str                       # район (для фильтра)
    address: str
    rating: float = 4.7


# --------------------------------------------------------------------------- #
#  Боксы
# --------------------------------------------------------------------------- #
class BoxCreate(BaseModel):
    """Партнёр публикует бокс."""

    partner_id: str
    category: BoxCategory = "sweet"
    title: str = ""
    price: int = Field(..., ge=100, description="Цена бокса, тг")
    value_est: int = Field(..., ge=100, description="Ориентировочная ценность содержимого, тг")
    qty: int = Field(..., ge=1, le=50)
    pickup_from: str                    # ISO datetime окна самовывоза
    pickup_to: str
    description: str = ""


class Box(CategoryLabeled):
    id: str
    partner_id: str
    partner_name: str
    district: str
    address: str
    rating: float
    title: str
    price: int
    value_est: int
    qty_total: int
    qty_left: int
    pickup_from: str
    pickup_to: str
    description: str
    created_at: datetime = Field(default_factory=_utcnow)

    @computed_field
    @property
    def discount(self) -> int:
        if self.value_est <= 0:
            return 0
        return round((1 - self.price / self.value_est) * 100)


# --------------------------------------------------------------------------- #
#  Заказы
# --------------------------------------------------------------------------- #
class OrderCreate(BaseModel):
    box_id: str
    user_name: str = Field(..., min_length=1)
    user_phone: str = Field(..., min_length=5)


class Order(CategoryLabeled):
    id: str
    code: str                           # код выдачи, напр. SB-7F3A
    box_id: str
    partner_id: str
    partner_name: str
    address: str
    price: int
    user_name: str
    user_phone: str
    status: OrderStatus
    pickup_from: str
    pickup_to: str
    created_at: datetime = Field(default_factory=_utcnow)


class OrderResult(BaseModel):
    order: Order
    qr_svg: str                         # QR с кодом выдачи (SVG)


class RedeemInput(BaseModel):
    code: str
