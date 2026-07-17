"""Pydantic-схемы API: партнёры, боксы, заказы."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

# Категории боксов из ТЗ
BoxCategory = Literal["sweet", "bakery", "mixed", "snack"]
OrderStatus = Literal[
    "payment_pending", "paid", "issued", "expired", "payment_failed", "refunded", "cancelled"
]

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


class PartnerApplication(BaseModel):
    user_id: str
    email: str
    email_verified: bool
    brand_name: str
    address: str
    district: str
    status: Literal["pending", "approved", "suspended", "rejected"]
    created_at: str


class PartnerStatusUpdate(BaseModel):
    status: Literal["pending", "approved", "suspended", "rejected"]
    reason: str = Field(default="", max_length=500)


class PartnerPaymentAccountCreate(BaseModel):
    partner_id: str = Field(..., min_length=1, max_length=64)
    provider: Literal["kaspi", "stripe"]
    merchant_reference: str = Field(..., min_length=2, max_length=200)
    point_of_service_id: str = Field(default="", max_length=200)
    credentials: str = Field(..., min_length=8, max_length=4000)


class PartnerPaymentAccount(BaseModel):
    id: str
    partner_id: str
    provider: str
    merchant_reference_masked: str
    point_of_service_id: str
    status: Literal["pending", "active", "suspended"]
    payments_enabled: bool
    refunds_enabled: bool
    credentials_configured: bool = True
    created_at: str
    updated_at: str
    verified_at: str | None = None
    verified_by: str | None = None


class PaymentAccountStatusUpdate(BaseModel):
    status: Literal["pending", "active", "suspended"]
    payments_enabled: bool = False
    refunds_enabled: bool = False
    reason: str = Field(..., min_length=3, max_length=500)


class CommissionRuleCreate(BaseModel):
    partner_id: str
    rate_basis_points: int = Field(..., ge=0, le=5000)


class StaffInvitationCreate(BaseModel):
    email: str = Field(..., max_length=254)
    partner_role: Literal["owner", "manager", "cashier"]
    partner_id: str | None = Field(default=None, max_length=64)
    brand_name: str = Field(default="", max_length=120)
    address: str = Field(default="", max_length=300)
    district: str = Field(default="", max_length=80)


class StaffInvitationResult(BaseModel):
    invite_url: str
    expires_in: int = 604800


class ManualEmailVerifyInput(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


# --------------------------------------------------------------------------- #
#  Боксы
# --------------------------------------------------------------------------- #
class BoxCreate(BaseModel):
    """Партнёр публикует бокс.

    ``partner_id`` остаётся в контракте для admin-инструментов и совместимости,
    но для роли partner сервер всегда сверяет его с заведением из аккаунта.
    """

    partner_id: str = Field(..., min_length=1, max_length=64)
    category: BoxCategory = "sweet"
    title: str = Field(default="", max_length=120)
    price: int = Field(..., ge=100, le=50_000, description="Цена бокса, тг")
    value_est: int = Field(..., ge=100, le=1_000_000,
                           description="Ориентировочная ценность содержимого, тг")
    qty: int = Field(..., ge=1, le=50)
    pickup_from: str                    # ISO datetime окна самовывоза
    pickup_to: str
    description: str = Field(default="", max_length=1_000)

    @model_validator(mode="after")
    def validate_pickup_window(self) -> "BoxCreate":
        """Окно должно быть timezone-aware, последовательным и ещё открытым."""
        try:
            start = datetime.fromisoformat(self.pickup_from.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.pickup_to.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError("окно самовывоза должно быть в ISO 8601") from exc
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("окно самовывоза должно содержать часовой пояс")
        if end <= start:
            raise ValueError("конец окна самовывоза должен быть позже начала")
        if end <= datetime.now(timezone.utc):
            raise ValueError("окно самовывоза уже завершилось")
        if end - start > timedelta(hours=24):
            raise ValueError("окно самовывоза не может быть длиннее 24 часов")
        return self


class BoxUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    price: int | None = Field(default=None, ge=100, le=50_000)
    value_est: int | None = Field(default=None, ge=100, le=1_000_000)
    qty_left: int | None = Field(default=None, ge=0, le=50)


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
    box_id: str = Field(..., min_length=1, max_length=64)
    user_name: str = Field(..., min_length=1, max_length=100)
    user_phone: str = Field(..., min_length=5, max_length=32)

    @model_validator(mode="after")
    def validate_contact(self) -> "OrderCreate":
        if not self.user_name.strip():
            raise ValueError("имя не может состоять из пробелов")
        phone = self.user_phone.strip()
        if any(ch not in "+0123456789 ()-" for ch in phone):
            raise ValueError("телефон содержит недопустимые символы")
        if sum(ch.isdigit() for ch in phone) < 5:
            raise ValueError("в телефоне недостаточно цифр")
        return self


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


class PublicOrder(BaseModel):
    """Безопасное представление заказа для гостевой проверки по коду.

    Имя, телефон и внутренний id намеренно отсутствуют. Полную модель получают
    только владелец аккаунта, своё заведение и администратор.
    """

    code: str
    partner_name: str
    address: str
    category: BoxCategory
    price: int
    status: OrderStatus
    pickup_from: str
    pickup_to: str

    @computed_field
    @property
    def category_ru(self) -> str:
        return CATEGORY_RU.get(self.category, self.category)

    @computed_field
    @property
    def emoji(self) -> str:
        return CATEGORY_EMOJI.get(self.category, "🧺")

    @classmethod
    def from_order(cls, order: Order) -> "PublicOrder":
        return cls(**order.model_dump(include={
            "code", "partner_name", "address", "category", "price", "status",
            "pickup_from", "pickup_to",
        }))


class OrderResult(BaseModel):
    order: Order
    qr_svg: str                         # QR с кодом выдачи (SVG)


class CheckoutSessionResult(BaseModel):
    order_id: str
    payment_id: str
    checkout_url: str
    reservation_expires_at: str


class CheckoutStatus(BaseModel):
    order_id: str
    payment_status: Literal["pending", "paid", "failed", "expired", "refunded"]
    order: PublicOrder | None = None
    qr_svg: str | None = None


class Payment(BaseModel):
    id: str
    order_id: str
    user_id: str | None = None
    provider: str
    status: str
    currency: str
    amount_minor: int
    checkout_session_id: str | None = None
    payment_intent_id: str | None = None
    idempotency_key: str
    reservation_expires_at: str
    created_at: str
    updated_at: str


class RedeemInput(BaseModel):
    code: str = Field(..., min_length=4, max_length=32)


# --------------------------------------------------------------------------- #
#  Отзывы (только по завершённому заказу — «купил и ввёл код»)
# --------------------------------------------------------------------------- #
class RefundRequestCreate(BaseModel):
    reason: Literal["not_issued", "venue_closed", "other"]
    details: str = Field(..., min_length=5, max_length=1000)


class RefundDecision(BaseModel):
    action: Literal["reviewing", "approve", "reject"]
    resolution: str = Field(..., min_length=3, max_length=1000)


class RefundRequest(BaseModel):
    id: str
    order_id: str
    user_id: str
    partner_id: str
    reason: str
    details: str
    status: Literal["pending", "reviewing", "rejected", "refunded"]
    resolution: str
    created_at: str
    updated_at: str
    resolved_by: str | None = None


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
