"""
Pydantic schemas for delivery tracking
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


# Driver schemas
class DriverLogin(BaseModel):
    """Driver login request"""
    phone: str = Field(..., min_length=10, max_length=20)
    password: str = Field(..., min_length=4)


class DriverResponse(BaseModel):
    """Driver information response"""
    id: int
    name: str
    phone: str
    vehicle_type: Optional[str] = None
    vehicle_plate: Optional[str] = None
    is_active: bool
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    last_location_update: Optional[datetime] = None

    class Config:
        from_attributes = True


class DriverTokenResponse(BaseModel):
    """Driver login token response"""
    access_token: str
    token_type: str = "bearer"
    driver: DriverResponse


class DriverCreate(BaseModel):
    """Create new driver"""
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)
    password: str = Field(..., min_length=4)
    vehicle_type: Optional[str] = Field(None, max_length=50)
    vehicle_plate: Optional[str] = Field(None, max_length=20)
    user_id: Optional[int] = None


class DriverUpdate(BaseModel):
    """Update driver information"""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    password: Optional[str] = Field(None, min_length=4)
    vehicle_type: Optional[str] = Field(None, max_length=50)
    vehicle_plate: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None


class DriverListResponse(BaseModel):
    """List of drivers"""
    drivers: List[DriverResponse]
    total: int


# Delivery schemas
class LocationUpdate(BaseModel):
    """GPS location update"""
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(None, ge=0)
    speed: Optional[float] = Field(None, ge=0)


class DeliveryCreate(BaseModel):
    """Create delivery for an order"""
    order_id: int
    driver_id: Optional[int] = None
    pickup_lat: Optional[float] = Field(None, ge=-90, le=90)
    pickup_lng: Optional[float] = Field(None, ge=-180, le=180)
    pickup_address: Optional[str] = Field(None, max_length=255)
    delivery_lat: Optional[float] = Field(None, ge=-90, le=90)
    delivery_lng: Optional[float] = Field(None, ge=-180, le=180)
    delivery_address: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class DeliveryAssign(BaseModel):
    """Assign delivery to driver"""
    driver_id: int


class DeliveryComplete(BaseModel):
    """Complete delivery"""
    notes: Optional[str] = None
    delivery_proof_photo: Optional[str] = None
    signature: Optional[str] = None


class LocationHistoryResponse(BaseModel):
    """Location history item"""
    id: int
    lat: float
    lng: float
    accuracy: Optional[float] = None
    speed: Optional[float] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class DeliveryResponse(BaseModel):
    """Delivery information"""
    id: int
    order_id: int
    driver_id: Optional[int] = None
    status: str
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    pickup_address: Optional[str] = None
    delivery_lat: Optional[float] = None
    delivery_lng: Optional[float] = None
    delivery_address: Optional[str] = None
    assigned_at: datetime
    started_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    notes: Optional[str] = None
    driver: Optional[DriverResponse] = None

    class Config:
        from_attributes = True


class DeliveryDetailResponse(DeliveryResponse):
    """Delivery with location history"""
    location_history: List[LocationHistoryResponse] = []

    class Config:
        from_attributes = True


class ActiveDeliveryResponse(BaseModel):
    """Active delivery with order and driver info"""
    id: int
    order_number: str
    customer_name: str
    customer_phone: str
    delivery_address: str
    delivery_city: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    driver_vehicle: Optional[str] = None
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    delivery_lat: Optional[float] = None
    delivery_lng: Optional[float] = None
    status: str
    assigned_at: datetime
    started_at: Optional[datetime] = None
    last_location_update: Optional[datetime] = None


class ActiveDeliveriesResponse(BaseModel):
    """List of active deliveries"""
    deliveries: List[ActiveDeliveryResponse]
    total: int


# WebSocket schemas
class WSLocationUpdate(BaseModel):
    """WebSocket location update message"""
    type: str = "location_update"
    delivery_id: int
    order_number: str
    lat: float
    lng: float
    timestamp: datetime
    driver_name: Optional[str] = None


class WSDeliveryStatus(BaseModel):
    """WebSocket delivery status update"""
    type: str = "status_update"
    delivery_id: int
    order_number: str
    status: str
    timestamp: datetime
