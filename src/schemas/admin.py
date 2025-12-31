"""
Admin Schemas - Pydantic models for admin validation
"""
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, EmailStr, Field


class AdminLogin(BaseModel):
    """Admin login request"""
    email: EmailStr
    password: str = Field(min_length=1)


class AdminResponse(BaseModel):
    """Admin user response"""
    email: str
    name: str
    is_admin: bool = True


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str = "bearer"
    user: AdminResponse


class OrderStatusUpdate(BaseModel):
    """Update order status"""
    status: Optional[Literal[
        "pending", "paid", "processing", "printing",
        "printed", "shipped", "delivered", "cancelled"
    ]] = None
    tracking_number: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=500)


class OrderSummary(BaseModel):
    """Order summary for lists"""
    order_number: str
    customer: str
    phone: str = ""
    email: str = ""
    items_count: int
    total: float
    status: str
    payment_status: str
    delivery_method: str
    delivery_city: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PaginationInfo(BaseModel):
    """Pagination metadata"""
    page: int
    per_page: int
    total: int
    pages: int


class OrderListResponse(BaseModel):
    """Paginated order list"""
    orders: List[OrderSummary]
    pagination: PaginationInfo


class OrderStats(BaseModel):
    """Order statistics"""
    total: int
    pending: int
    processing: int
    completed: int
    today: int


class RevenueStats(BaseModel):
    """Revenue statistics"""
    total: float
    today: float
    month: float
    currency: str = "KES"


class RecentOrder(BaseModel):
    """Recent order for dashboard"""
    order_number: str
    customer: str
    total: float
    status: str
    payment_status: str
    created_at: datetime


class DashboardResponse(BaseModel):
    """Dashboard statistics"""
    orders: OrderStats
    revenue: RevenueStats
    cards_printed: int
    recent_orders: List[RecentOrder]


class MessageResponse(BaseModel):
    """Contact message response"""
    id: int
    name: str
    email: str
    phone: Optional[str] = None
    subject: Optional[str] = None
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Paginated message list"""
    messages: List[MessageResponse]
    pagination: PaginationInfo
    unread_count: int


class PrintQueueItem(BaseModel):
    """Print queue item"""
    id: int
    order_number: str
    copies: int
    status: str
    created_at: datetime


class PrintQueueResponse(BaseModel):
    """Print queue response"""
    queue: List[PrintQueueItem]
