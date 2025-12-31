"""
PrintKe Database Models
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

db = SQLAlchemy()


def generate_uuid():
    return str(uuid.uuid4())[:8].upper()


class User(UserMixin, db.Model):
    """User model for customers and admins"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, default=generate_uuid)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256))
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    company_name = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    orders = db.relationship('Order', backref='customer', lazy='dynamic')
    addresses = db.relationship('Address', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.email


class Address(db.Model):
    """Delivery addresses"""
    __tablename__ = 'addresses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    label = db.Column(db.String(50))  # Home, Office, etc.
    address_line1 = db.Column(db.String(200), nullable=False)
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100), nullable=False)
    county = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CardTemplate(db.Model):
    """Pre-designed card templates"""
    __tablename__ = 'card_templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # school, corporate, church, gym, event
    description = db.Column(db.Text)
    front_image = db.Column(db.String(255))
    back_image = db.Column(db.String(255))
    preview_image = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    is_premium = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Product(db.Model):
    """Card products/types"""
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    card_type = db.Column(db.String(50), default='pvc')  # pvc, smart, rfid
    is_double_sided = db.Column(db.Boolean, default=True)
    base_price = db.Column(db.Float, default=300)  # KES
    image = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order_items = db.relationship('OrderItem', backref='product', lazy='dynamic')


class Order(db.Model):
    """Customer orders"""
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Guest checkout info
    guest_email = db.Column(db.String(120))
    guest_phone = db.Column(db.String(20))
    guest_name = db.Column(db.String(100))

    # Order status
    status = db.Column(db.String(50), default='pending')
    # pending, paid, processing, printing, printed, shipped, delivered, cancelled

    # Pricing
    subtotal = db.Column(db.Float, default=0)
    delivery_fee = db.Column(db.Float, default=0)
    discount = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

    # Delivery
    delivery_method = db.Column(db.String(50), default='delivery')  # delivery, pickup
    delivery_address = db.Column(db.Text)
    delivery_city = db.Column(db.String(100))
    delivery_notes = db.Column(db.Text)
    tracking_number = db.Column(db.String(100))

    # Payment
    payment_method = db.Column(db.String(50))  # mpesa, card, bank
    payment_status = db.Column(db.String(50), default='pending')
    payment_reference = db.Column(db.String(100))
    paid_at = db.Column(db.DateTime)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    printed_at = db.Column(db.DateTime)
    shipped_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)

    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='order', lazy='dynamic')

    @staticmethod
    def generate_order_number():
        """Generate unique order number like PK-240101-ABCD"""
        date_part = datetime.now().strftime('%y%m%d')
        random_part = str(uuid.uuid4())[:4].upper()
        return f"PK-{date_part}-{random_part}"


class OrderItem(db.Model):
    """Individual items in an order"""
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))

    # Card details
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)

    # Design files
    front_image_original = db.Column(db.String(255))
    back_image_original = db.Column(db.String(255))
    front_image_processed = db.Column(db.String(255))
    back_image_processed = db.Column(db.String(255))
    pdf_file = db.Column(db.String(255))

    # Template used (if any)
    template_id = db.Column(db.Integer, db.ForeignKey('card_templates.id'))

    # Custom fields for the card
    custom_data = db.Column(db.JSON)  # name, id_number, photo, etc.

    # Status
    status = db.Column(db.String(50), default='pending')
    printed_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    template = db.relationship('CardTemplate')


class Payment(db.Model):
    """Payment transactions"""
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    transaction_id = db.Column(db.String(100), unique=True)
    payment_method = db.Column(db.String(50), nullable=False)  # mpesa, card

    # M-Pesa specific
    mpesa_receipt = db.Column(db.String(50))
    phone_number = db.Column(db.String(20))
    checkout_request_id = db.Column(db.String(100))
    merchant_request_id = db.Column(db.String(100))

    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, completed, failed
    error_message = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)


class PrintJob(db.Model):
    """Print queue management"""
    __tablename__ = 'print_jobs'

    id = db.Column(db.Integer, primary_key=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_items.id'), nullable=False)
    job_id = db.Column(db.String(100))  # CUPS job ID
    status = db.Column(db.String(50), default='queued')  # queued, printing, completed, failed
    copies = db.Column(db.Integer, default=1)
    error_message = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    order_item = db.relationship('OrderItem')


class ContactMessage(db.Model):
    """Contact form submissions"""
    __tablename__ = 'contact_messages'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    replied_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Coupon(db.Model):
    """Discount coupons"""
    __tablename__ = 'coupons'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), default='percentage')  # percentage, fixed
    discount_value = db.Column(db.Float, nullable=False)
    min_order_amount = db.Column(db.Float, default=0)
    max_uses = db.Column(db.Integer)
    uses_count = db.Column(db.Integer, default=0)
    valid_from = db.Column(db.DateTime, default=datetime.utcnow)
    valid_until = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_valid(self):
        if not self.is_active:
            return False
        if self.max_uses and self.uses_count >= self.max_uses:
            return False
        now = datetime.utcnow()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True
