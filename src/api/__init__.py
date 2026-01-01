"""
API Routers for PrintKe
"""
from fastapi import APIRouter

from src.api.orders import router as orders_router
from src.api.payments import router as payments_router
from src.api.admin import router as admin_router
from src.api.drivers import router as drivers_router
from src.api.websockets import router as websockets_router

api_router = APIRouter()

api_router.include_router(orders_router, prefix="/orders", tags=["orders"])
api_router.include_router(payments_router, prefix="/payments", tags=["payments"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(drivers_router, prefix="/drivers", tags=["drivers"])
api_router.include_router(websockets_router, prefix="/ws", tags=["websockets"])
