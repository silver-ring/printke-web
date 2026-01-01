"""
Order API Routes - FastAPI
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models import Order, OrderItem
from src.schemas.orders import (
    OrderCreate, OrderResponse, OrderCreateResponse, OrderItemResponse,
    PricingResponse, CalculatePriceRequest, CalculatePriceResponse
)
from src.core.config import settings
from src.services.card_processor import CardProcessor

router = APIRouter()


def get_price_per_card(quantity: int) -> float:
    """Calculate price per card based on quantity tier"""
    for tier in settings.pricing_tiers.values():
        if tier["min"] <= quantity <= tier["max"]:
            return tier["price"]
    return 400  # Default price


@router.post("/create", response_model=OrderCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    front: UploadFile = File(..., description="Front image file"),
    name: str = Form(..., min_length=2, max_length=100),
    phone: str = Form(...),
    delivery_address: str = Form(..., min_length=10, max_length=500),
    delivery_city: str = Form(default="nairobi"),
    quantity: int = Form(default=1, ge=1, le=10000),
    email: Optional[str] = Form(default=None),
    back: Optional[UploadFile] = File(default=None, description="Back image file"),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new order with card images

    - **front**: Front image file (required)
    - **back**: Back image file (optional)
    - **name**: Customer name
    - **phone**: Customer phone (Kenyan format)
    - **quantity**: Number of cards (1-10000)
    - **delivery_address**: Full delivery address
    - **delivery_city**: City for delivery fee calculation
    """
    # Validate file types
    allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}

    front_ext = front.filename.rsplit(".", 1)[-1].lower() if "." in front.filename else ""
    if front_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid front image type. Allowed: {', '.join(allowed_extensions)}"
        )

    if back and back.filename:
        back_ext = back.filename.rsplit(".", 1)[-1].lower() if "." in back.filename else ""
        if back_ext not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid back image type. Allowed: {', '.join(allowed_extensions)}"
            )

    # Format phone number
    import re
    phone_clean = re.sub(r'[\s\-\(\)\.]', '', phone)
    if phone_clean.startswith('+'):
        phone_clean = phone_clean[1:]
    if phone_clean.startswith('0'):
        phone_clean = '254' + phone_clean[1:]
    elif phone_clean.startswith('7') or phone_clean.startswith('1'):
        phone_clean = '254' + phone_clean

    if not re.match(r'^254[17]\d{8}$', phone_clean):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number. Use format: 0712345678"
        )

    # Generate order number and create folder
    order_number = Order.generate_order_number()
    order_folder = os.path.join(settings.upload_folder, order_number)
    os.makedirs(order_folder, exist_ok=True)

    # Save original files
    front_orig = os.path.join(order_folder, "front_original.png")
    with open(front_orig, "wb") as f:
        content = await front.read()
        f.write(content)

    back_orig = None
    if back and back.filename:
        back_orig = os.path.join(order_folder, "back_original.png")
        with open(back_orig, "wb") as f:
            content = await back.read()
            f.write(content)

    # Process images
    processor = CardProcessor(settings.upload_folder, os.path.join(settings.upload_folder, "processed"))

    front_processed = os.path.join(order_folder, "front_card.png")
    processor.resize_image(front_orig, front_processed)

    back_processed = None
    pdf_path = os.path.join(order_folder, f"{order_number}.pdf")

    if back_orig:
        back_processed = os.path.join(order_folder, "back_card.png")
        processor.resize_image(back_orig, back_processed)
        processor.create_card_pdf(front_processed, back_processed, pdf_path)
    else:
        processor.create_single_side_pdf(front_processed, pdf_path)

    # Calculate pricing
    unit_price = get_price_per_card(quantity)
    subtotal = unit_price * quantity
    delivery_fee = settings.delivery_fees.get(delivery_city.lower(), settings.delivery_fees.get("other", 1000))
    total = subtotal + delivery_fee

    # Create order in database
    order = Order(
        order_number=order_number,
        guest_name=name.strip(),
        guest_email=email.lower().strip() if email else None,
        guest_phone=phone_clean,
        status="pending",
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=total,
        delivery_method="delivery",
        delivery_address=delivery_address.strip(),
        delivery_city=delivery_city
    )
    db.add(order)
    await db.flush()

    # Create order item
    order_item = OrderItem(
        order_id=order.id,
        quantity=quantity,
        unit_price=unit_price,
        total_price=subtotal,
        front_image_original=front_orig,
        back_image_original=back_orig,
        front_image_processed=front_processed,
        back_image_processed=back_processed,
        pdf_file=pdf_path
    )
    db.add(order_item)
    await db.commit()

    return OrderCreateResponse(
        order_number=order_number,
        quantity=quantity,
        unit_price=unit_price,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=total,
        preview_url=f"/api/orders/{order_number}/preview",
        payment_url=f"/payment/{order_number}"
    )


@router.get("/{order_number}", response_model=OrderResponse)
async def get_order(order_number: str, db: AsyncSession = Depends(get_db)):
    """Get order details by order number"""
    # Handle DEMO order for testing
    if order_number == "DEMO":
        shipped_time = datetime.utcnow() - timedelta(minutes=10)
        return OrderResponse(
            order_number="DEMO",
            status="shipped",
            payment_status="paid",
            subtotal=2000,
            delivery_fee=300,
            discount=0,
            total=2300,
            delivery_method="delivery",
            delivery_city="nairobi_cbd",
            delivery_address="Kenyatta Avenue, Nairobi CBD",
            tracking_number="PKE-DEMO-001",
            created_at=shipped_time - timedelta(hours=2),
            paid_at=shipped_time - timedelta(hours=1, minutes=50),
            printed_at=shipped_time - timedelta(minutes=30),
            shipped_at=shipped_time,
            items=[OrderItemResponse(
                quantity=5,
                unit_price=400,
                total_price=2000,
                status="shipped"
            )]
        )

    result = await db.execute(
        select(Order)
        .where(Order.order_number == order_number)
        .options(selectinload(Order.items))
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # Get items
    items = []
    for item in order.items:
        items.append(OrderItemResponse(
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.total_price,
            status=item.status,
            has_front=bool(item.front_image_processed),
            has_back=bool(item.back_image_processed),
            has_pdf=bool(item.pdf_file)
        ))

    return OrderResponse(
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        subtotal=order.subtotal,
        delivery_fee=order.delivery_fee,
        discount=order.discount,
        total=order.total,
        delivery_method=order.delivery_method,
        delivery_city=order.delivery_city,
        delivery_address=order.delivery_address,
        tracking_number=order.tracking_number,
        created_at=order.created_at,
        paid_at=order.paid_at,
        printed_at=order.printed_at,
        shipped_at=order.shipped_at,
        delivered_at=order.delivered_at,
        items=items
    )


@router.get("/{order_number}/preview")
async def preview_order(order_number: str, db: AsyncSession = Depends(get_db)):
    """Get PDF preview for order"""
    result = await db.execute(
        select(Order)
        .where(Order.order_number == order_number)
        .options(selectinload(Order.items))
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if not order.items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No items in order")

    item = order.items[0]
    if not item.pdf_file or not os.path.exists(item.pdf_file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF not found")

    return FileResponse(item.pdf_file, media_type="application/pdf")


@router.get("/{order_number}/download")
async def download_order(order_number: str, db: AsyncSession = Depends(get_db)):
    """Download PDF for order"""
    result = await db.execute(
        select(Order)
        .where(Order.order_number == order_number)
        .options(selectinload(Order.items))
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if not order.items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No items in order")

    item = order.items[0]
    if not item.pdf_file or not os.path.exists(item.pdf_file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF not found")

    return FileResponse(
        item.pdf_file,
        media_type="application/pdf",
        filename=f"card_{order_number}.pdf"
    )


@router.get("/pricing", response_model=PricingResponse)
async def get_pricing():
    """Get pricing tiers and delivery fees"""
    return PricingResponse(
        pricing_tiers=settings.pricing_tiers,
        delivery_fees=settings.delivery_fees
    )


@router.post("/calculate", response_model=CalculatePriceResponse)
async def calculate_price(request: CalculatePriceRequest):
    """Calculate price for given quantity and delivery city"""
    unit_price = get_price_per_card(request.quantity)
    subtotal = unit_price * request.quantity
    delivery_fee = settings.delivery_fees.get(
        request.delivery_city.lower(),
        settings.delivery_fees.get("other", 1000)
    )
    total = subtotal + delivery_fee

    return CalculatePriceResponse(
        quantity=request.quantity,
        unit_price=unit_price,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=total
    )
