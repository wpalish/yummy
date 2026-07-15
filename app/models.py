"""Pydantic-схемы API: партнёры, боксы, заказы."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, computed_field

# Категории боксов из ТЗ
BoxCategory = Literal["sweet", "bakery", "mixed", "snack"]
OrderStatus = Literal["paid", "issued", "expired", "refunded", "cancelled"]

CATEGORY_RU = {
    "sweet": "Сладкий бокс",
    "bakery": "Бокс выпечки",
    "mixed": "Микс-бокс",
    "snack": "Снек-бокс",
}
CATEGORY_EMOJI = {"sweet": "🍩", "bakery": "🥐", "mixed": "🧺", "snack": "🥪"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
#  Партнёры
# --------------------------------------------------------------------------- #
class Partner(BaseModel):
    id: str
    name: str
    district: str                       # район (для фильтра)
    address: str
    rating: float = 4.7
    lat: float = 51.128                 # координаты для карты
    lng: float = 71.430


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


class BoxTemplateCreate(BaseModel):
    """Шаблон бокса: партнёр сохраняет и публикует одной кнопкой каждый вечер."""

    partner_id: str
    category: BoxCategory = "sweet"
    title: str = ""
    price: int = Field(..., ge=100)
    value_est: int = Field(..., ge=100)
    qty: int = Field(..., ge=1, le=50)
    hours: int = Field(4, ge=1, le=12, description="Забрать до N часов от публикации")
    description: str = ""


class Box(BaseModel):
    id: str
    partner_id: str
    partner_name: str
    district: str
    address: str
    rating: float
    category: BoxCategory
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

    @computed_field
    @property
    def category_ru(self) -> str:
        return CATEGORY_RU.get(self.category, self.category)

    @computed_field
    @property
    def emoji(self) -> str:
        return CATEGORY_EMOJI.get(self.category, "🧺")


# --------------------------------------------------------------------------- #
#  Заказы
# --------------------------------------------------------------------------- #
class OrderCreate(BaseModel):
    box_id: str
    user_name: str = Field(..., min_length=1)
    user_phone: str = Field(..., min_length=5)


class Order(BaseModel):
    id: str
    code: str                           # код выдачи, напр. SB-7F3A
    box_id: str
    partner_id: str
    partner_name: str
    address: str
    category: BoxCategory
    price: int
    user_name: str
    user_phone: str
    status: OrderStatus
    pickup_from: str
    pickup_to: str
    created_at: datetime = Field(default_factory=_utcnow)

    @computed_field
    @property
    def category_ru(self) -> str:
        return CATEGORY_RU.get(self.category, self.category)

    @computed_field
    @property
    def emoji(self) -> str:
        return CATEGORY_EMOJI.get(self.category, "🧺")


class OrderResult(BaseModel):
    order: Order
    qr_svg: str                         # QR с кодом выдачи (SVG)


class RedeemInput(BaseModel):
    code: str


# --------------------------------------------------------------------------- #
#  Отзывы (только по завершённому заказу — «купил и ввёл код»)
# --------------------------------------------------------------------------- #
class ReviewCreate(BaseModel):
    order_id: str
    rating: int = Field(..., ge=1, le=5)
    text: str = Field(..., min_length=3, max_length=500)


class Review(BaseModel):
    id: str
    partner_id: str
    order_id: str
    author_name: str
    rating: int
    text: str
    status: Literal["approved", "pending", "rejected"]
    created_at: str


# --------------------------------------------------------------------------- #
#  AI-помощники
# --------------------------------------------------------------------------- #
class BoxDescribeInput(BaseModel):
    category: BoxCategory = "sweet"
    notes: str = Field(..., min_length=2, max_length=300)


class BoxDescribeResult(BaseModel):
    description: str
    ai: bool                            # True — сгенерировано моделью, False — фолбэк-шаблон
