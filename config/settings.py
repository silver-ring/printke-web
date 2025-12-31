"""
PrintKe Configuration Settings
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'printke-secret-key-change-in-production')

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///printke.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # File uploads
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # CR80 Card specifications
    CARD_WIDTH_PX = 1012  # pixels at 300 DPI
    CARD_HEIGHT_PX = 638
    CARD_WIDTH_INCH = 3.375
    CARD_HEIGHT_INCH = 2.125
    CARD_DPI = 300

    # Printing
    MOCK_PRINTING = os.getenv('MOCK_PRINTING', 'true').lower() == 'true'
    PRINTER_NAME = os.getenv('PRINTER_NAME', 'LXM-Card-Printer')

    # M-Pesa Configuration
    MPESA_CONSUMER_KEY = os.getenv('MPESA_CONSUMER_KEY', '')
    MPESA_CONSUMER_SECRET = os.getenv('MPESA_CONSUMER_SECRET', '')
    MPESA_SHORTCODE = os.getenv('MPESA_SHORTCODE', '')
    MPESA_PASSKEY = os.getenv('MPESA_PASSKEY', '')
    MPESA_CALLBACK_URL = os.getenv('MPESA_CALLBACK_URL', '')
    MPESA_ENV = os.getenv('MPESA_ENV', 'sandbox')  # sandbox or production

    # Pricing (in KES) - Based on Nairobi market research Dec 2024
    # Market reference: Vexar KES 150/card, PrintShopKE KES 12-14/card
    # Premium for online ordering, design processing, and convenience
    PRICING_TIERS = {
        'single': {'min': 1, 'max': 10, 'price': 400},      # Small orders, high handling cost
        'small': {'min': 11, 'max': 50, 'price': 300},      # Still small, premium service
        'medium': {'min': 51, 'max': 200, 'price': 200},    # Standard orders
        'standard': {'min': 201, 'max': 500, 'price': 150}, # Competitive with Vexar
        'large': {'min': 501, 'max': 1000, 'price': 120},   # Bulk discount
        'bulk': {'min': 1001, 'max': 999999, 'price': 100}, # Major discount for institutions
    }

    # Delivery fees (in KES) - We deliver everywhere, no pickup
    DELIVERY_FEES = {
        'nairobi_cbd': 200,     # CBD - boda boda
        'nairobi': 300,         # Greater Nairobi
        'nakuru': 500,          # Nearby major town
        'mombasa': 700,         # Coast - courier
        'kisumu': 700,          # Western - courier
        'eldoret': 600,         # North Rift
        'thika': 350,           # Nairobi satellite
        'other': 1000,          # Other counties
    }

    # Email
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')

    # Business info
    BUSINESS_NAME = 'PrintKe'
    BUSINESS_PHONE = os.getenv('BUSINESS_PHONE', '+254700000000')
    BUSINESS_EMAIL = os.getenv('BUSINESS_EMAIL', 'info@printke.co.ke')
    BUSINESS_ADDRESS = 'Nairobi, Kenya'


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    MOCK_PRINTING = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    MOCK_PRINTING = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    MOCK_PRINTING = True


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
