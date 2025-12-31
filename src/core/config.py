"""
Application Configuration using Pydantic Settings
"""
from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment"""

    # App
    app_name: str = "PrintKe"
    debug: bool = False
    environment: str = "development"

    # Security
    secret_key: str = "printke-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Database
    database_url: str = "sqlite+aiosqlite:///./printke.db"

    # CORS
    cors_origins: List[str] = ["*"]

    # M-Pesa
    mpesa_consumer_key: str = ""
    mpesa_consumer_secret: str = ""
    mpesa_shortcode: str = ""
    mpesa_passkey: str = ""
    mpesa_callback_url: str = ""
    mpesa_env: str = "sandbox"

    # Printing
    mock_printing: bool = True
    printer_name: str = "LXM-Card-Printer"

    # File uploads
    upload_folder: str = "./uploads"
    max_file_size: int = 16 * 1024 * 1024  # 16MB

    # Card specifications (CR80)
    card_width_px: int = 1012
    card_height_px: int = 638
    card_dpi: int = 300

    # Pricing (KES)
    pricing_tiers: dict = {
        "single": {"min": 1, "max": 10, "price": 400},
        "small": {"min": 11, "max": 50, "price": 300},
        "medium": {"min": 51, "max": 200, "price": 200},
        "standard": {"min": 201, "max": 500, "price": 150},
        "large": {"min": 501, "max": 1000, "price": 120},
        "bulk": {"min": 1001, "max": 999999, "price": 100},
    }

    # Delivery fees (KES)
    delivery_fees: dict = {
        "nairobi_cbd": 200,
        "nairobi": 300,
        "nakuru": 500,
        "mombasa": 700,
        "kisumu": 700,
        "eldoret": 600,
        "thika": 350,
        "other": 1000,
    }

    # Business info
    business_name: str = "PrintKe"
    business_phone: str = "+254700000000"
    business_email: str = "info@printke.co.ke"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()
