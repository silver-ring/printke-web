"""
Admin API Routes - FastAPI with JWT Authentication
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models import Order, OrderItem, User, Payment, PrintJob, ContactMessage, Driver, Delivery, LocationHistory
from src.schemas.admin import (
    AdminLogin, AdminResponse, TokenResponse, OrderStatusUpdate,
    DashboardResponse, OrderStats, RevenueStats, RecentOrder,
    OrderListResponse, OrderSummary, PaginationInfo,
    MessageListResponse, MessageResponse, PrintQueueResponse, PrintQueueItem
)
from src.schemas.delivery import (
    DriverCreate, DriverUpdate, DriverResponse, DriverListResponse,
    DeliveryCreate, DeliveryAssign, ActiveDeliveryResponse, ActiveDeliveriesResponse
)
from src.core.security import (
    authenticate_user, create_access_token, get_current_admin,
    get_password_hash
)
from src.core.config import settings
from src.services.card_processor import PrintService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/login", response_model=TokenResponse)
async def admin_login(request: AdminLogin, db: AsyncSession = Depends(get_db)):
    """
    Admin login endpoint - returns JWT token

    - **email**: Admin email
    - **password**: Admin password
    """
    user = await authenticate_user(db, request.email, request.password)

    if not user:
        logger.warning(f"Failed login attempt for: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    access_token = create_access_token(data={"sub": user.email})
    logger.info(f"Admin login: {user.email}")

    return TokenResponse(
        access_token=access_token,
        user=AdminResponse(email=user.email, name=user.full_name)
    )


@router.get("/me", response_model=AdminResponse)
async def get_current_admin_info(current_user: User = Depends(get_current_admin)):
    """Get current admin user info"""
    return AdminResponse(
        email=current_user.email,
        name=current_user.full_name,
        is_admin=current_user.is_admin
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get dashboard statistics"""
    today = datetime.utcnow().date()
    month_ago = today - timedelta(days=30)

    # Order statistics
    total_orders = (await db.execute(select(func.count(Order.id)))).scalar() or 0
    pending_orders = (await db.execute(
        select(func.count(Order.id)).where(Order.status == "pending")
    )).scalar() or 0
    processing_orders = (await db.execute(
        select(func.count(Order.id)).where(Order.status.in_(["paid", "processing", "printing"]))
    )).scalar() or 0
    completed_orders = (await db.execute(
        select(func.count(Order.id)).where(Order.status == "delivered")
    )).scalar() or 0

    # Today's orders
    today_orders = (await db.execute(
        select(func.count(Order.id)).where(func.date(Order.created_at) == today)
    )).scalar() or 0

    # Revenue
    total_revenue = (await db.execute(
        select(func.sum(Order.total)).where(Order.payment_status == "paid")
    )).scalar() or 0

    today_revenue = (await db.execute(
        select(func.sum(Order.total)).where(
            Order.payment_status == "paid",
            func.date(Order.paid_at) == today
        )
    )).scalar() or 0

    month_revenue = (await db.execute(
        select(func.sum(Order.total)).where(
            Order.payment_status == "paid",
            Order.paid_at >= datetime.combine(month_ago, datetime.min.time())
        )
    )).scalar() or 0

    # Cards printed
    total_cards = (await db.execute(
        select(func.sum(OrderItem.quantity))
        .join(Order)
        .where(Order.status.in_(["printed", "shipped", "delivered"]))
    )).scalar() or 0

    # Recent orders
    recent_result = await db.execute(
        select(Order)
        .options(selectinload(Order.customer))
        .order_by(Order.created_at.desc())
        .limit(10)
    )
    recent_orders = recent_result.scalars().all()

    return DashboardResponse(
        orders=OrderStats(
            total=total_orders,
            pending=pending_orders,
            processing=processing_orders,
            completed=completed_orders,
            today=today_orders
        ),
        revenue=RevenueStats(
            total=float(total_revenue),
            today=float(today_revenue),
            month=float(month_revenue)
        ),
        cards_printed=total_cards or 0,
        recent_orders=[
            RecentOrder(
                order_number=o.order_number,
                customer=o.guest_name or (o.customer.full_name if o.customer else "Guest"),
                total=float(o.total),
                status=o.status,
                payment_status=o.payment_status,
                created_at=o.created_at
            ) for o in recent_orders
        ]
    )


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """List all orders with filtering and pagination"""
    query = select(Order)

    if status:
        query = query.where(Order.status == status)
    if payment_status:
        query = query.where(Order.payment_status == payment_status)
    if search:
        search_term = f"%{search.strip()[:100]}%"
        query = query.where(
            or_(
                Order.order_number.ilike(search_term),
                Order.guest_name.ilike(search_term),
                Order.guest_phone.ilike(search_term),
                Order.guest_email.ilike(search_term)
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.options(selectinload(Order.items), selectinload(Order.customer))
    query = query.order_by(Order.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    orders = result.scalars().all()

    return OrderListResponse(
        orders=[
            OrderSummary(
                order_number=o.order_number,
                customer=o.guest_name or (o.customer.full_name if o.customer else "Guest"),
                phone=o.guest_phone or (o.customer.phone if o.customer else ""),
                email=o.guest_email or (o.customer.email if o.customer else ""),
                items_count=len(o.items),
                total=float(o.total),
                status=o.status,
                payment_status=o.payment_status,
                delivery_method=o.delivery_method,
                delivery_city=o.delivery_city,
                created_at=o.created_at
            ) for o in orders
        ],
        pagination=PaginationInfo(
            page=page,
            per_page=per_page,
            total=total,
            pages=(total + per_page - 1) // per_page
        )
    )


@router.get("/orders/{order_number}")
async def get_order_detail(
    order_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get detailed order information"""
    result = await db.execute(
        select(Order)
        .where(Order.order_number == order_number)
        .options(
            selectinload(Order.items),
            selectinload(Order.payments),
            selectinload(Order.customer)
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    items = [{
        "id": item.id,
        "quantity": item.quantity,
        "unit_price": float(item.unit_price),
        "total_price": float(item.total_price),
        "status": item.status,
        "printed_count": item.printed_count,
        "has_front": bool(item.front_image_processed),
        "has_back": bool(item.back_image_processed),
        "has_pdf": bool(item.pdf_file)
    } for item in order.items]

    payments = [{
        "transaction_id": p.transaction_id,
        "method": p.payment_method,
        "amount": float(p.amount),
        "status": p.status,
        "receipt": p.mpesa_receipt,
        "created_at": p.created_at.isoformat()
    } for p in order.payments]

    return {
        "order_number": order.order_number,
        "customer": {
            "name": order.guest_name or (order.customer.full_name if order.customer else ""),
            "email": order.guest_email or (order.customer.email if order.customer else ""),
            "phone": order.guest_phone or (order.customer.phone if order.customer else "")
        },
        "status": order.status,
        "payment_status": order.payment_status,
        "subtotal": float(order.subtotal),
        "delivery_fee": float(order.delivery_fee),
        "discount": float(order.discount),
        "total": float(order.total),
        "delivery": {
            "method": order.delivery_method,
            "address": order.delivery_address,
            "city": order.delivery_city,
            "notes": order.delivery_notes,
            "tracking": order.tracking_number
        },
        "items": items,
        "payments": payments,
        "timestamps": {
            "created": order.created_at.isoformat(),
            "paid": order.paid_at.isoformat() if order.paid_at else None,
            "printed": order.printed_at.isoformat() if order.printed_at else None,
            "shipped": order.shipped_at.isoformat() if order.shipped_at else None,
            "delivered": order.delivered_at.isoformat() if order.delivered_at else None
        }
    }


@router.put("/orders/{order_number}/status")
async def update_order_status(
    order_number: str,
    request: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update order status"""
    result = await db.execute(
        select(Order).where(Order.order_number == order_number)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    old_status = order.status

    if request.status:
        order.status = request.status

        # Update timestamps
        if request.status == "printed" and not order.printed_at:
            order.printed_at = datetime.utcnow()
        elif request.status == "shipped" and not order.shipped_at:
            order.shipped_at = datetime.utcnow()
        elif request.status == "delivered" and not order.delivered_at:
            order.delivered_at = datetime.utcnow()

    if request.tracking_number:
        order.tracking_number = request.tracking_number

    if request.notes:
        order.delivery_notes = request.notes

    await db.commit()

    logger.info(f"Order {order_number} status changed: {old_status} -> {request.status} by {current_user.email}")

    return {
        "success": True,
        "order_number": order.order_number,
        "status": order.status
    }


@router.post("/orders/{order_number}/print")
async def print_order(
    order_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Send order to printer"""
    result = await db.execute(
        select(Order)
        .where(Order.order_number == order_number)
        .options(selectinload(Order.items))
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if not order.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No items in order")

    item = order.items[0]
    if not item.pdf_file or not os.path.exists(item.pdf_file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF file not found")

    printer = PrintService(
        printer_name=settings.printer_name,
        mock_mode=settings.mock_printing
    )

    print_result = printer.print_card(item.pdf_file, copies=item.quantity)

    if print_result["success"]:
        order.status = "printing"
        item.status = "printing"

        print_job = PrintJob(
            order_item_id=item.id,
            job_id=print_result.get("job_id"),
            copies=item.quantity,
            status="printing" if not print_result.get("mock") else "completed"
        )
        db.add(print_job)
        await db.commit()

        logger.info(f"Print job started for order {order_number} by {current_user.email}")

    return print_result


@router.get("/print-queue", response_model=PrintQueueResponse)
async def get_print_queue(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get print queue status"""
    from src.models import OrderItem
    result = await db.execute(
        select(PrintJob)
        .where(PrintJob.status.in_(["queued", "printing"]))
        .options(selectinload(PrintJob.order_item).selectinload(OrderItem.order))
        .order_by(PrintJob.created_at)
    )
    jobs = result.scalars().all()

    return PrintQueueResponse(
        queue=[
            PrintQueueItem(
                id=job.id,
                order_number=job.order_item.order.order_number,
                copies=job.copies,
                status=job.status,
                created_at=job.created_at
            ) for job in jobs
        ]
    )


@router.get("/messages", response_model=MessageListResponse)
async def list_messages(
    page: int = Query(default=1, ge=1),
    unread: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """List contact messages"""
    query = select(ContactMessage)

    if unread:
        query = query.where(ContactMessage.is_read == False)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Count unread
    unread_count = (await db.execute(
        select(func.count(ContactMessage.id)).where(ContactMessage.is_read == False)
    )).scalar() or 0

    # Paginate
    query = query.order_by(ContactMessage.created_at.desc())
    query = query.offset((page - 1) * 20).limit(20)

    result = await db.execute(query)
    messages = result.scalars().all()

    return MessageListResponse(
        messages=[MessageResponse.model_validate(m) for m in messages],
        pagination=PaginationInfo(
            page=page,
            per_page=20,
            total=total,
            pages=(total + 19) // 20
        ),
        unread_count=unread_count
    )


@router.put("/messages/{message_id}/read")
async def mark_message_read(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Mark message as read"""
    result = await db.execute(select(ContactMessage).where(ContactMessage.id == message_id))
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    message.is_read = True
    await db.commit()

    return {"success": True}


# ===== DELIVERY & DRIVER MANAGEMENT =====

@router.get("/drivers", response_model=DriverListResponse)
async def list_drivers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """List all drivers"""
    result = await db.execute(
        select(Driver).order_by(Driver.created_at.desc())
    )
    drivers = result.scalars().all()

    return DriverListResponse(
        drivers=[DriverResponse.model_validate(d) for d in drivers],
        total=len(drivers)
    )


@router.post("/drivers", response_model=DriverResponse)
async def create_driver(
    driver_data: DriverCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a new driver"""
    # Check if phone already exists
    result = await db.execute(select(Driver).where(Driver.phone == driver_data.phone))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Driver with this phone number already exists"
        )

    # Create driver
    driver = Driver(
        name=driver_data.name,
        phone=driver_data.phone,
        password_hash=get_password_hash(driver_data.password),
        vehicle_type=driver_data.vehicle_type,
        vehicle_plate=driver_data.vehicle_plate,
        user_id=driver_data.user_id,
        is_active=True
    )

    db.add(driver)
    await db.commit()
    await db.refresh(driver)

    logger.info(f"Driver created: {driver.name} by {current_user.email}")

    return DriverResponse.model_validate(driver)


@router.get("/drivers/{driver_id}", response_model=DriverResponse)
async def get_driver(
    driver_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get driver details"""
    result = await db.execute(select(Driver).where(Driver.id == driver_id))
    driver = result.scalar_one_or_none()

    if not driver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

    return DriverResponse.model_validate(driver)


@router.put("/drivers/{driver_id}", response_model=DriverResponse)
async def update_driver(
    driver_id: int,
    driver_data: DriverUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update driver information"""
    result = await db.execute(select(Driver).where(Driver.id == driver_id))
    driver = result.scalar_one_or_none()

    if not driver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

    # Update fields if provided
    if driver_data.name is not None:
        driver.name = driver_data.name
    if driver_data.phone is not None:
        # Check if phone is already used by another driver
        result = await db.execute(
            select(Driver).where(Driver.phone == driver_data.phone, Driver.id != driver_id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number already in use"
            )
        driver.phone = driver_data.phone
    if driver_data.password is not None:
        driver.password_hash = get_password_hash(driver_data.password)
    if driver_data.vehicle_type is not None:
        driver.vehicle_type = driver_data.vehicle_type
    if driver_data.vehicle_plate is not None:
        driver.vehicle_plate = driver_data.vehicle_plate
    if driver_data.is_active is not None:
        driver.is_active = driver_data.is_active

    await db.commit()
    await db.refresh(driver)

    logger.info(f"Driver updated: {driver.name} by {current_user.email}")

    return DriverResponse.model_validate(driver)


@router.delete("/drivers/{driver_id}")
async def delete_driver(
    driver_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Delete a driver"""
    result = await db.execute(select(Driver).where(Driver.id == driver_id))
    driver = result.scalar_one_or_none()

    if not driver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

    # Check if driver has active deliveries
    result = await db.execute(
        select(func.count(Delivery.id)).where(
            Delivery.driver_id == driver_id,
            Delivery.status.in_(["assigned", "in_transit"])
        )
    )
    active_deliveries = result.scalar() or 0

    if active_deliveries > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete driver with {active_deliveries} active deliveries"
        )

    await db.delete(driver)
    await db.commit()

    logger.info(f"Driver deleted: {driver.name} by {current_user.email}")

    return {"success": True, "message": "Driver deleted"}


@router.post("/orders/{order_number}/assign")
async def assign_order_to_driver(
    order_number: str,
    assignment: DeliveryAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign an order to a driver for delivery"""
    # Get order
    result = await db.execute(
        select(Order).where(Order.order_number == order_number)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # Check order status
    if order.status not in ["paid", "processing", "printed", "shipped"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot assign delivery for order in status: {order.status}"
        )

    # Get driver
    result = await db.execute(select(Driver).where(Driver.id == assignment.driver_id))
    driver = result.scalar_one_or_none()

    if not driver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

    if not driver.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Driver is not active"
        )

    # Check if delivery already exists
    result = await db.execute(
        select(Delivery).where(Delivery.order_id == order.id)
    )
    existing_delivery = result.scalar_one_or_none()

    if existing_delivery:
        # Update existing delivery
        existing_delivery.driver_id = driver.id
        existing_delivery.status = "assigned"
        existing_delivery.assigned_at = datetime.utcnow()
        delivery = existing_delivery
    else:
        # Create new delivery
        delivery = Delivery(
            order_id=order.id,
            driver_id=driver.id,
            status="assigned",
            delivery_address=order.delivery_address,
            assigned_at=datetime.utcnow()
        )
        db.add(delivery)

    # Update order status
    if order.status != "shipped":
        order.status = "shipped"
        order.shipped_at = datetime.utcnow()

    await db.commit()
    await db.refresh(delivery)

    logger.info(f"Order {order_number} assigned to driver {driver.name} by {current_user.email}")

    return {
        "success": True,
        "delivery_id": delivery.id,
        "order_number": order.order_number,
        "driver_name": driver.name,
        "status": delivery.status
    }


@router.get("/deliveries/active", response_model=ActiveDeliveriesResponse)
async def get_active_deliveries(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all active deliveries with real-time locations"""
    result = await db.execute(
        select(Delivery)
        .where(Delivery.status.in_(["assigned", "in_transit"]))
        .options(
            selectinload(Delivery.order),
            selectinload(Delivery.driver)
        )
        .order_by(Delivery.assigned_at.desc())
    )
    deliveries = result.scalars().all()

    active_deliveries = []
    for d in deliveries:
        order = d.order
        driver = d.driver

        active_deliveries.append(ActiveDeliveryResponse(
            id=d.id,
            order_number=order.order_number,
            customer_name=order.guest_name or "Guest",
            customer_phone=order.guest_phone or "",
            delivery_address=order.delivery_address or "",
            delivery_city=order.delivery_city,
            driver_name=driver.name if driver else None,
            driver_phone=driver.phone if driver else None,
            driver_vehicle=f"{driver.vehicle_type} - {driver.vehicle_plate}" if driver and driver.vehicle_type else None,
            current_lat=driver.current_lat if driver else None,
            current_lng=driver.current_lng if driver else None,
            delivery_lat=d.delivery_lat,
            delivery_lng=d.delivery_lng,
            status=d.status,
            assigned_at=d.assigned_at,
            started_at=d.started_at,
            last_location_update=driver.last_location_update if driver else None
        ))

    return ActiveDeliveriesResponse(
        deliveries=active_deliveries,
        total=len(active_deliveries)
    )
