"""
Order Schemas - Pydantic models for order validation
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr, field_validator
import re

from src.schemas.common import KenyanPhone, DeliveryCity


class OrderCreate(BaseModel):
    """Schema for creating a new order (form data, not JSON)"""
    name: str = Field(min_length=2, max_length=100)
    phone: KenyanPhone
    email: Optional[EmailStr] = None
    quantity: int = Field(ge=1, le=10000, default=1)
    delivery_address: str = Field(min_length=10, max_length=500)
    delivery_city: DeliveryCity = "nairobi"

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        # Remove potential XSS vectors
        if re.search(r'[<>{}]', v):
            raise ValueError("Invalid characters in name")
        return v.strip()

    @field_validator('delivery_address')
    @classmethod
    def validate_address(cls, v: str) -> str:
        # Basic sanitization
        v = re.sub(r'<[^>]*>', '', v)  # Remove HTML tags
        return v.strip()


class OrderItemResponse(BaseModel):
    """Order item in response"""
    quantity: int
    unit_price: float
    total_price: float
    status: str
    has_front: bool = False
    has_back: bool = False
    has_pdf: bool = False

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    """Order response schema"""
    order_number: str
    status: str
    payment_status: str
    subtotal: float
    delivery_fee: float
    discount: float
    total: float
    delivery_method: str
    delivery_city: Optional[str] = None
    delivery_address: Optional[str] = None
    tracking_number: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    printed_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    items: List[OrderItemResponse] = []

    class Config:
        from_attributes = True


class OrderCreateResponse(BaseModel):
    """Response after creating an order"""
    success: bool = True
    order_number: str
    quantity: int
    unit_price: float
    subtotal: float
    delivery_fee: float
    total: float
    preview_url: str
    payment_url: str
    message: str = "Order created successfully"


class PricingTier(BaseModel):
    """Pricing tier"""
    min: int
    max: int
    price: float


class PricingResponse(BaseModel):
    """Pricing information response"""
    pricing_tiers: dict[str, PricingTier]
    delivery_fees: dict[str, float]
    currency: str = "KES"


class CalculatePriceRequest(BaseModel):
    """Request to calculate price"""
    quantity: int = Field(ge=1, le=10000)
    delivery_city: DeliveryCity = "nairobi"


class CalculatePriceResponse(BaseModel):
    """Price calculation response"""
    quantity: int
    unit_price: float
    subtotal: float
    delivery_fee: float
    total: float
    currency: str = "KES"
