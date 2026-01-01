"""
WebSocket endpoint for real-time delivery tracking
"""
import logging
import json
from typing import Dict, Set
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import get_db, async_session_maker
from src.models import Delivery, Driver

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time delivery tracking"""

    def __init__(self):
        # Active connections: {order_number: set of websockets}
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # All connections for broadcast
        self.all_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, order_number: str = None):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        self.all_connections.add(websocket)

        if order_number:
            if order_number not in self.active_connections:
                self.active_connections[order_number] = set()
            self.active_connections[order_number].add(websocket)

        logger.info(f"WebSocket connected for order: {order_number or 'admin'}")

    def disconnect(self, websocket: WebSocket, order_number: str = None):
        """Remove a WebSocket connection"""
        self.all_connections.discard(websocket)

        if order_number and order_number in self.active_connections:
            self.active_connections[order_number].discard(websocket)
            if not self.active_connections[order_number]:
                del self.active_connections[order_number]

        logger.info(f"WebSocket disconnected for order: {order_number or 'admin'}")

    async def send_message(self, message: dict, websocket: WebSocket):
        """Send message to a specific websocket"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def broadcast_to_order(self, order_number: str, message: dict):
        """Broadcast message to all connections watching a specific order"""
        if order_number in self.active_connections:
            dead_connections = set()
            for connection in self.active_connections[order_number]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to order {order_number}: {e}")
                    dead_connections.add(connection)

            # Clean up dead connections
            for connection in dead_connections:
                self.disconnect(connection, order_number)

    async def broadcast_to_all(self, message: dict):
        """Broadcast message to all connected clients (admin dashboard)"""
        dead_connections = set()
        for connection in self.all_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to all: {e}")
                dead_connections.add(connection)

        # Clean up dead connections
        for connection in dead_connections:
            if connection in self.all_connections:
                self.all_connections.discard(connection)


# Global connection manager
manager = ConnectionManager()


@router.websocket("/deliveries")
async def delivery_tracking_websocket(websocket: WebSocket, order_number: str = None):
    """
    WebSocket endpoint for real-time delivery tracking

    Query parameters:
    - order_number: Track specific order (for customers)
    - If no order_number, receives all updates (for admin dashboard)

    Messages sent to clients:
    - location_update: Driver location update
    - status_update: Delivery status change
    - delivery_assigned: Order assigned to driver
    - delivery_started: Driver started delivery
    - delivery_completed: Delivery completed
    """
    await manager.connect(websocket, order_number)

    try:
        # Send initial connection confirmation
        await manager.send_message({
            "type": "connected",
            "order_number": order_number,
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)

        # If tracking specific order, send current status
        if order_number:
            async with async_session_maker() as db:
                result = await db.execute(
                    select(Delivery)
                    .join(Delivery.order)
                    .where(Delivery.order.has(order_number=order_number))
                    .options(
                        selectinload(Delivery.driver),
                        selectinload(Delivery.order)
                    )
                )
                delivery = result.scalar_one_or_none()

                if delivery:
                    # Send current delivery status
                    status_message = {
                        "type": "current_status",
                        "delivery_id": delivery.id,
                        "order_number": order_number,
                        "status": delivery.status,
                        "assigned_at": delivery.assigned_at.isoformat(),
                        "started_at": delivery.started_at.isoformat() if delivery.started_at else None,
                        "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
                    }

                    if delivery.driver:
                        status_message["driver"] = {
                            "name": delivery.driver.name,
                            "phone": delivery.driver.phone,
                            "vehicle": delivery.driver.vehicle_type,
                            "current_lat": delivery.driver.current_lat,
                            "current_lng": delivery.driver.current_lng,
                            "last_update": delivery.driver.last_location_update.isoformat() if delivery.driver.last_location_update else None
                        }

                    await manager.send_message(status_message, websocket)

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            # Echo back for ping/pong
            await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})

    except WebSocketDisconnect:
        manager.disconnect(websocket, order_number)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, order_number)


async def broadcast_location_update(delivery_id: int, order_number: str, lat: float, lng: float, driver_name: str = None):
    """
    Broadcast location update to all subscribers

    Called from driver API when location is updated
    """
    message = {
        "type": "location_update",
        "delivery_id": delivery_id,
        "order_number": order_number,
        "lat": lat,
        "lng": lng,
        "driver_name": driver_name,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Broadcast to specific order watchers
    await manager.broadcast_to_order(order_number, message)

    # Broadcast to admin dashboard
    await manager.broadcast_to_all(message)


async def broadcast_status_update(delivery_id: int, order_number: str, status: str, driver_name: str = None):
    """
    Broadcast delivery status update

    Called when delivery status changes (assigned, started, completed, etc.)
    """
    message = {
        "type": "status_update",
        "delivery_id": delivery_id,
        "order_number": order_number,
        "status": status,
        "driver_name": driver_name,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Broadcast to specific order watchers
    await manager.broadcast_to_order(order_number, message)

    # Broadcast to admin dashboard
    await manager.broadcast_to_all(message)
