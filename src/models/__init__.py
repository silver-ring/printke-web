"""
PrintKe Database Models - SQLAlchemy with FastAPI
"""
from datetime import datetime
from typing import Optional, List
import uuid

from sqlalchemy import String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())[:8].upper()


class User(Base):
    """User model for customers and admins"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(256))
    first_name: Mapped[Optional[str]] = mapped_column(String(50))
    last_name: Mapped[Optional[str]] = mapped_column(String(50))
    company_name: Mapped[Optional[str]] = mapped_column(String(100))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    orders: Mapped[List["Order"]] = relationship(back_populates="customer")
    addresses: Mapped[List["Address"]] = relationship(back_populates="user")

    @property
    def full_name(self) -> str:
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.email


class Address(Base):
    """Delivery addresses"""
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(50))
    address_line1: Mapped[str] = mapped_column(String(200), nullable=False)
    address_line2: Mapped[Optional[str]] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    county: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="addresses")


class Product(Base):
    """Card products/types"""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    card_type: Mapped[str] = mapped_column(String(50), default="pvc")
    is_double_sided: Mapped[bool] = mapped_column(Boolean, default=True)
    base_price: Mapped[float] = mapped_column(Float, default=300)
    image: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    order_items: Mapped[List["OrderItem"]] = relationship(back_populates="product")


class Order(Base):
    """Customer orders"""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))

    # Guest checkout info
    guest_email: Mapped[Optional[str]] = mapped_column(String(120))
    guest_phone: Mapped[Optional[str]] = mapped_column(String(20))
    guest_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Order status
    status: Mapped[str] = mapped_column(String(50), default="pending")

    # Pricing
    subtotal: Mapped[float] = mapped_column(Float, default=0)
    delivery_fee: Mapped[float] = mapped_column(Float, default=0)
    discount: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)

    # Delivery
    delivery_method: Mapped[str] = mapped_column(String(50), default="delivery")
    delivery_address: Mapped[Optional[str]] = mapped_column(Text)
    delivery_city: Mapped[Optional[str]] = mapped_column(String(100))
    delivery_notes: Mapped[Optional[str]] = mapped_column(Text)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100))

    # Payment
    payment_method: Mapped[Optional[str]] = mapped_column(String(50))
    payment_status: Mapped[str] = mapped_column(String(50), default="pending")
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    printed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    customer: Mapped[Optional["User"]] = relationship(back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[List["Payment"]] = relationship(back_populates="order")

    @staticmethod
    def generate_order_number() -> str:
        """Generate unique order number like PK-240101-ABCD"""
        date_part = datetime.now().strftime("%y%m%d")
        random_part = str(uuid.uuid4())[:4].upper()
        return f"PK-{date_part}-{random_part}"


class OrderItem(Base):
    """Individual items in an order"""
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("products.id"))

    # Card details
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)

    # Design files
    front_image_original: Mapped[Optional[str]] = mapped_column(String(255))
    back_image_original: Mapped[Optional[str]] = mapped_column(String(255))
    front_image_processed: Mapped[Optional[str]] = mapped_column(String(255))
    back_image_processed: Mapped[Optional[str]] = mapped_column(String(255))
    pdf_file: Mapped[Optional[str]] = mapped_column(String(255))

    # Custom fields for the card
    custom_data: Mapped[Optional[dict]] = mapped_column(JSON)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="pending")
    printed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped[Optional["Product"]] = relationship(back_populates="order_items")
    print_jobs: Mapped[List["PrintJob"]] = relationship(back_populates="order_item")


class Payment(Base):
    """Payment transactions"""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)

    # M-Pesa specific
    mpesa_receipt: Mapped[Optional[str]] = mapped_column(String(50))
    phone_number: Mapped[Optional[str]] = mapped_column(String(20))
    checkout_request_id: Mapped[Optional[str]] = mapped_column(String(100))
    merchant_request_id: Mapped[Optional[str]] = mapped_column(String(100))

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    order: Mapped["Order"] = relationship(back_populates="payments")


class PrintJob(Base):
    """Print queue management"""
    __tablename__ = "print_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("order_items.id"), nullable=False)
    job_id: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="queued")
    copies: Mapped[int] = mapped_column(Integer, default=1)
    error_message: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    order_item: Mapped["OrderItem"] = relationship(back_populates="print_jobs")


class ContactMessage(Base):
    """Contact form submissions"""
    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    subject: Mapped[Optional[str]] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
