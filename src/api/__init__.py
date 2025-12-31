"""
API Routers for PrintKe
"""
from fastapi import APIRouter

from src.api.orders import router as orders_router
from src.api.payments import router as payments_router
from src.api.admin import router as admin_router

api_router = APIRouter()

api_router.include_router(orders_router, prefix="/orders", tags=["orders"])
api_router.include_router(payments_router, prefix="/payments", tags=["payments"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
