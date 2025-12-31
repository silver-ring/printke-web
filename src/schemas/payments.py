"""
Payment Schemas - Pydantic models for payment validation
"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel

from src.schemas.common import KenyanPhone, OrderNumber


class PaymentInitiate(BaseModel):
    """Request to initiate M-Pesa payment"""
    order_number: OrderNumber
    phone: KenyanPhone


class PaymentResponse(BaseModel):
    """Response after initiating payment"""
    success: bool
    message: str
    checkout_request_id: Optional[str] = None
    mock: bool = False
    receipt: Optional[str] = None
    auto_printed: bool = False


class PaymentStatusResponse(BaseModel):
    """Payment status response"""
    order_number: str
    payment_status: str
    order_status: str
    total: float
    paid_at: Optional[datetime] = None
    receipt: Optional[str] = None


class MpesaCallbackItem(BaseModel):
    """M-Pesa callback metadata item"""
    Name: str
    Value: Any = None


class MpesaCallbackMetadata(BaseModel):
    """M-Pesa callback metadata"""
    Item: list[MpesaCallbackItem] = []


class MpesaStkCallback(BaseModel):
    """M-Pesa STK callback body"""
    MerchantRequestID: str
    CheckoutRequestID: str
    ResultCode: int
    ResultDesc: str
    CallbackMetadata: Optional[MpesaCallbackMetadata] = None


class MpesaCallbackBody(BaseModel):
    """M-Pesa callback body wrapper"""
    stkCallback: MpesaStkCallback


class MpesaCallback(BaseModel):
    """M-Pesa callback request"""
    Body: MpesaCallbackBody
