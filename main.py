"""
PrintKe - Kenya's Premier Online Card Printing Service
FastAPI Application Entry Point
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.database import init_db, async_session_maker
from src.api import api_router
from src.core.config import settings
from src.core.security import get_password_hash
from src.models import User, Product

# Setup logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    # Startup
    logger.info("Starting PrintKe application...")

    # Create upload directories
    os.makedirs(settings.upload_folder, exist_ok=True)
    os.makedirs(os.path.join(settings.upload_folder, "originals"), exist_ok=True)
    os.makedirs(os.path.join(settings.upload_folder, "processed"), exist_ok=True)
    os.makedirs(os.path.join(settings.upload_folder, "pdfs"), exist_ok=True)

    # Initialize database
    await init_db()

    # Create default admin user if not exists
    async with async_session_maker() as db:
        from sqlalchemy import select

        result = await db.execute(select(User).where(User.email == "admin@printke.co.ke"))
        if not result.scalar_one_or_none():
            admin = User(
                email="admin@printke.co.ke",
                phone="+254700000000",
                first_name="Admin",
                last_name="PrintKe",
                is_admin=True,
                password_hash=get_password_hash("admin123")  # Change in production!
            )
            db.add(admin)
            await db.commit()
            logger.info("Created default admin user")

        # Create default products if not exist
        result = await db.execute(select(Product).limit(1))
        if not result.scalar_one_or_none():
            products = [
                Product(
                    name="Standard PVC ID Card",
                    slug="standard-pvc",
                    description="High-quality CR80 PVC card with full-color printing",
                    card_type="pvc",
                    is_double_sided=True,
                    base_price=300
                ),
                Product(
                    name="Single-Sided Card",
                    slug="single-sided",
                    description="Single-sided CR80 PVC card",
                    card_type="pvc",
                    is_double_sided=False,
                    base_price=200
                ),
                Product(
                    name="Premium Matte Card",
                    slug="premium-matte",
                    description="Premium matte finish CR80 card",
                    card_type="pvc",
                    is_double_sided=True,
                    base_price=350
                ),
            ]
            for product in products:
                db.add(product)
            await db.commit()
            logger.info("Created default products")

    logger.info(f"PrintKe started - MOCK MODE: {settings.mock_printing}")

    yield

    # Shutdown
    logger.info("Shutting down PrintKe application...")


# Create FastAPI app
app = FastAPI(
    title="PrintKe API",
    description="Kenya's Premier Online Card Printing Service",
    version="2.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    # Security headers
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # CSP and HSTS in production
    if not settings.debug:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://*.tile.openstreetmap.org; "
            "connect-src 'self'"
        )
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Include API routers
app.include_router(api_router, prefix="/api")


# Web routes (HTML pages)
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("customer/index.html", {"request": request})


@app.get("/order", response_class=HTMLResponse)
async def order_page(request: Request):
    return templates.TemplateResponse("customer/order.html", {"request": request})


@app.get("/order/{order_number}", response_class=HTMLResponse)
async def order_status(request: Request, order_number: str):
    return templates.TemplateResponse("customer/tracking.html", {"request": request, "order_number": order_number})


@app.get("/track/{order_number}", response_class=HTMLResponse)
async def tracking_page(request: Request, order_number: str):
    return templates.TemplateResponse("customer/tracking.html", {"request": request, "order_number": order_number})


@app.get("/payment/{order_number}", response_class=HTMLResponse)
async def payment_page(request: Request, order_number: str):
    return templates.TemplateResponse("customer/payment.html", {"request": request, "order_number": order_number})


@app.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request):
    return templates.TemplateResponse("customer/pricing.html", {"request": request})


@app.get("/templates", response_class=HTMLResponse)
async def card_templates(request: Request):
    return templates.TemplateResponse("customer/templates.html", {"request": request})


@app.get("/contact", response_class=HTMLResponse)
async def contact(request: Request):
    return templates.TemplateResponse("customer/contact.html", {"request": request})


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("customer/about.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})


@app.get("/admin/orders", response_class=HTMLResponse)
async def admin_orders(request: Request):
    return templates.TemplateResponse("admin/orders.html", {"request": request})


@app.get("/admin/orders/{order_number}", response_class=HTMLResponse)
async def admin_order_detail(request: Request, order_number: str):
    return templates.TemplateResponse("admin/order_detail.html", {"request": request, "order_number": order_number})


# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "mock_mode": settings.mock_printing}


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return templates.TemplateResponse("errors/404.html", {"request": request}, status_code=404)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    logger.error(f"Server error: {exc}", exc_info=True)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"error": "Internal server error"})
    return templates.TemplateResponse("errors/500.html", {"request": request}, status_code=500)


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  PrintKe - Kenya's Premier Card Printing Service")
    print(f"  MOCK MODE: {settings.mock_printing}")
    print("  API Docs: http://localhost:8000/docs")
    print("=" * 60)

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
