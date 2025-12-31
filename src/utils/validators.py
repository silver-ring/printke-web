"""
Input Validation Utilities
"""
import re
from functools import wraps
from flask import request, jsonify


class ValidationError(Exception):
    """Custom validation error"""
    def __init__(self, message, field=None):
        self.message = message
        self.field = field
        super().__init__(message)


def validate_phone(phone):
    """
    Validate and format Kenyan phone number
    Returns formatted number (254XXXXXXXXX) or raises ValidationError
    """
    if not phone:
        raise ValidationError("Phone number is required", "phone")

    # Remove spaces, dashes, and other characters
    phone = re.sub(r'[\s\-\(\)\.]', '', str(phone))

    # Handle different formats
    if phone.startswith('+'):
        phone = phone[1:]

    if phone.startswith('0'):
        phone = '254' + phone[1:]
    elif phone.startswith('7') or phone.startswith('1'):
        phone = '254' + phone

    # Validate format
    if not re.match(r'^254[17]\d{8}$', phone):
        raise ValidationError("Invalid phone number. Use format: 0712345678", "phone")

    return phone


def validate_email(email):
    """Validate email format"""
    if not email:
        return None  # Email is optional

    email = str(email).strip().lower()
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(pattern, email):
        raise ValidationError("Invalid email format", "email")

    return email


def validate_quantity(quantity, min_qty=1, max_qty=10000):
    """Validate order quantity"""
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        raise ValidationError("Quantity must be a number", "quantity")

    if qty < min_qty:
        raise ValidationError(f"Minimum quantity is {min_qty}", "quantity")

    if qty > max_qty:
        raise ValidationError(f"Maximum quantity is {max_qty}", "quantity")

    return qty


def validate_name(name, field_name="name", required=True, min_length=2, max_length=100):
    """Validate name field"""
    if not name:
        if required:
            raise ValidationError(f"{field_name.title()} is required", field_name)
        return None

    name = str(name).strip()

    if len(name) < min_length:
        raise ValidationError(f"{field_name.title()} must be at least {min_length} characters", field_name)

    if len(name) > max_length:
        raise ValidationError(f"{field_name.title()} must be less than {max_length} characters", field_name)

    # Check for suspicious characters (basic XSS prevention)
    if re.search(r'[<>{}]', name):
        raise ValidationError(f"Invalid characters in {field_name}", field_name)

    return name


def validate_address(address, required=True):
    """Validate delivery address"""
    if not address:
        if required:
            raise ValidationError("Delivery address is required", "delivery_address")
        return None

    address = str(address).strip()

    if len(address) < 10:
        raise ValidationError("Please provide a complete delivery address", "delivery_address")

    if len(address) > 500:
        raise ValidationError("Address is too long", "delivery_address")

    return address


def validate_delivery_city(city, valid_cities=None):
    """Validate delivery city"""
    if not city:
        raise ValidationError("Delivery city is required", "delivery_city")

    city = str(city).strip().lower()

    if valid_cities and city not in valid_cities:
        raise ValidationError(f"Invalid delivery city", "delivery_city")

    return city


def validate_order_number(order_number):
    """Validate order number format"""
    if not order_number:
        raise ValidationError("Order number is required", "order_number")

    # Expected format: PK-YYMMDD-XXXX
    pattern = r'^PK-\d{6}-[A-Z0-9]{4}$'

    if order_number == 'DEMO':
        return order_number

    if not re.match(pattern, order_number):
        raise ValidationError("Invalid order number format", "order_number")

    return order_number


def validate_file_upload(file, allowed_extensions=None, max_size_mb=16):
    """Validate uploaded file"""
    if not file or file.filename == '':
        raise ValidationError("File is required", "file")

    # Check extension
    if allowed_extensions:
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in allowed_extensions:
            raise ValidationError(
                f"Invalid file type. Allowed: {', '.join(allowed_extensions)}",
                "file"
            )

    # Check file size (read first chunk)
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Reset to beginning

    max_size_bytes = max_size_mb * 1024 * 1024
    if size > max_size_bytes:
        raise ValidationError(f"File too large. Maximum size: {max_size_mb}MB", "file")

    return True


def validate_json_payload(required_fields=None, optional_fields=None):
    """
    Decorator to validate JSON request payload
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            data = request.get_json()

            if data is None:
                return jsonify({'error': 'JSON payload required'}), 400

            # Check required fields
            if required_fields:
                missing = [field for field in required_fields if field not in data or not data[field]]
                if missing:
                    return jsonify({
                        'error': f"Missing required fields: {', '.join(missing)}",
                        'missing_fields': missing
                    }), 400

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def sanitize_string(value, max_length=1000):
    """Sanitize string input to prevent XSS"""
    if value is None:
        return None

    value = str(value).strip()

    # Remove potential XSS vectors
    value = re.sub(r'<[^>]*>', '', value)  # Remove HTML tags
    value = value.replace('&', '&amp;')
    value = value.replace('<', '&lt;')
    value = value.replace('>', '&gt;')
    value = value.replace('"', '&quot;')
    value = value.replace("'", '&#x27;')

    # Truncate if too long
    if len(value) > max_length:
        value = value[:max_length]

    return value
