"""
Driver API Routes - For delivery drivers
"""
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models import Driver, Delivery, LocationHistory, Order
from src.schemas.delivery import (
    DriverLogin, DriverTokenResponse, DriverResponse,
    DeliveryResponse, LocationUpdate, DeliveryComplete
)
from src.core.security import (
    verify_password, create_access_token, decode_token
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter()
logger = logging.getLogger(__name__)
security = HTTPBearer()


async def get_current_driver(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Driver:
    """Get current authenticated driver from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        raise credentials_exception

    driver_id: int = payload.get("driver_id")
    if driver_id is None:
        raise credentials_exception

    result = await db.execute(select(Driver).where(Driver.id == driver_id))
    driver = result.scalar_one_or_none()

    if driver is None:
        raise credentials_exception

    if not driver.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive driver"
        )

    return driver


@router.post("/login", response_model=DriverTokenResponse)
async def driver_login(request: DriverLogin, db: AsyncSession = Depends(get_db)):
    """
    Driver login endpoint - returns JWT token

    - **phone**: Driver phone number
    - **password**: Driver password
    """
    # Find driver by phone
    result = await db.execute(select(Driver).where(Driver.phone == request.phone))
    driver = result.scalar_one_or_none()

    if not driver:
        logger.warning(f"Failed login attempt for driver: {request.phone}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone or password"
        )

    if not driver.password_hash or not verify_password(request.password, driver.password_hash):
        logger.warning(f"Invalid password for driver: {request.phone}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone or password"
        )

    if not driver.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Driver account is inactive"
        )

    # Create access token with driver_id
    access_token = create_access_token(data={"driver_id": driver.id, "phone": driver.phone})
    logger.info(f"Driver login: {driver.name} ({driver.phone})")

    return DriverTokenResponse(
        access_token=access_token,
        driver=DriverResponse.model_validate(driver)
    )


@router.get("/me", response_model=DriverResponse)
async def get_current_driver_info(current_driver: Driver = Depends(get_current_driver)):
    """Get current driver information"""
    return DriverResponse.model_validate(current_driver)


@router.get("/deliveries", response_model=List[DeliveryResponse])
async def get_driver_deliveries(
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get driver's assigned deliveries

    Returns all deliveries assigned to the current driver that are not yet completed
    """
    result = await db.execute(
        select(Delivery)
        .where(
            Delivery.driver_id == current_driver.id,
            Delivery.status.in_(["assigned", "in_transit"])
        )
        .options(selectinload(Delivery.order))
        .order_by(Delivery.assigned_at.desc())
    )
    deliveries = result.scalars().all()

    return [DeliveryResponse.model_validate(d) for d in deliveries]


@router.post("/deliveries/{delivery_id}/start")
async def start_delivery(
    delivery_id: int,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Start a delivery

    Marks the delivery as in_transit and records the start time
    """
    # Get delivery
    result = await db.execute(
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .options(selectinload(Delivery.order))
    )
    delivery = result.scalar_one_or_none()

    if not delivery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    # Verify this delivery belongs to current driver
    if delivery.driver_id != current_driver.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This delivery is not assigned to you"
        )

    # Check if already started
    if delivery.status == "in_transit":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Delivery already started"
        )

    if delivery.status == "delivered":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Delivery already completed"
        )

    # Update delivery status
    delivery.status = "in_transit"
    delivery.started_at = datetime.utcnow()

    # Update order status
    delivery.order.status = "in_transit"

    await db.commit()
    await db.refresh(delivery)

    logger.info(f"Delivery {delivery_id} started by driver {current_driver.name}")

    return {
        "success": True,
        "delivery_id": delivery.id,
        "status": delivery.status,
        "started_at": delivery.started_at.isoformat()
    }


@router.post("/deliveries/{delivery_id}/location")
async def update_delivery_location(
    delivery_id: int,
    location: LocationUpdate,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Update GPS location for active delivery

    Records the driver's current location in the delivery's location history
    """
    # Get delivery
    result = await db.execute(
        select(Delivery).where(Delivery.id == delivery_id)
    )
    delivery = result.scalar_one_or_none()

    if not delivery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    # Verify this delivery belongs to current driver
    if delivery.driver_id != current_driver.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This delivery is not assigned to you"
        )

    # Only update location for active deliveries
    if delivery.status not in ["assigned", "in_transit"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update location for completed delivery"
        )

    # Update driver's current location
    current_driver.current_lat = location.lat
    current_driver.current_lng = location.lng
    current_driver.last_location_update = datetime.utcnow()

    # Add to location history
    location_history = LocationHistory(
        delivery_id=delivery.id,
        lat=location.lat,
        lng=location.lng,
        accuracy=location.accuracy,
        speed=location.speed,
        timestamp=datetime.utcnow()
    )
    db.add(location_history)

    await db.commit()

    logger.debug(f"Location updated for delivery {delivery_id}: ({location.lat}, {location.lng})")

    return {
        "success": True,
        "delivery_id": delivery.id,
        "location": {
            "lat": location.lat,
            "lng": location.lng,
            "timestamp": location_history.timestamp.isoformat()
        }
    }


@router.post("/deliveries/{delivery_id}/complete")
async def complete_delivery(
    delivery_id: int,
    completion: DeliveryComplete,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Complete a delivery

    Marks the delivery as delivered and records completion time
    """
    # Get delivery
    result = await db.execute(
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .options(selectinload(Delivery.order))
    )
    delivery = result.scalar_one_or_none()

    if not delivery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    # Verify this delivery belongs to current driver
    if delivery.driver_id != current_driver.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This delivery is not assigned to you"
        )

    # Check if already completed
    if delivery.status == "delivered":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Delivery already completed"
        )

    # Update delivery
    delivery.status = "delivered"
    delivery.delivered_at = datetime.utcnow()
    if completion.notes:
        delivery.notes = completion.notes
    if completion.delivery_proof_photo:
        delivery.delivery_proof_photo = completion.delivery_proof_photo
    if completion.signature:
        delivery.signature = completion.signature

    # Update order status
    delivery.order.status = "delivered"
    delivery.order.delivered_at = datetime.utcnow()

    await db.commit()
    await db.refresh(delivery)

    logger.info(f"Delivery {delivery_id} completed by driver {current_driver.name}")

    return {
        "success": True,
        "delivery_id": delivery.id,
        "order_number": delivery.order.order_number,
        "status": delivery.status,
        "delivered_at": delivery.delivered_at.isoformat()
    }


@router.get("/deliveries/{delivery_id}")
async def get_delivery_detail(
    delivery_id: int,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed delivery information including order details"""
    result = await db.execute(
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .options(
            selectinload(Delivery.order),
            selectinload(Delivery.location_history)
        )
    )
    delivery = result.scalar_one_or_none()

    if not delivery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    # Verify this delivery belongs to current driver
    if delivery.driver_id != current_driver.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This delivery is not assigned to you"
        )

    order = delivery.order

    return {
        "delivery": {
            "id": delivery.id,
            "status": delivery.status,
            "pickup_address": delivery.pickup_address,
            "delivery_address": delivery.delivery_address,
            "delivery_lat": delivery.delivery_lat,
            "delivery_lng": delivery.delivery_lng,
            "assigned_at": delivery.assigned_at.isoformat(),
            "started_at": delivery.started_at.isoformat() if delivery.started_at else None,
            "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
            "notes": delivery.notes
        },
        "order": {
            "order_number": order.order_number,
            "customer_name": order.guest_name,
            "customer_phone": order.guest_phone,
            "total": float(order.total),
            "delivery_notes": order.delivery_notes
        }
    }
