"""
Common Pydantic Types and Validators
"""
import re
from typing import Annotated, Literal
from pydantic import BaseModel, Field, field_validator, BeforeValidator


# Custom validator for Kenyan phone numbers
def validate_kenyan_phone(v: str) -> str:
    """Validate and format Kenyan phone number to 254XXXXXXXXX"""
    if not v:
        raise ValueError("Phone number is required")

    # Remove spaces, dashes, and other characters
    phone = re.sub(r'[\s\-\(\)\.]', '', str(v))

    # Handle different formats
    if phone.startswith('+'):
        phone = phone[1:]

    if phone.startswith('0'):
        phone = '254' + phone[1:]
    elif phone.startswith('7') or phone.startswith('1'):
        phone = '254' + phone

    # Validate format
    if not re.match(r'^254[17]\d{8}$', phone):
        raise ValueError("Invalid phone number. Use format: 0712345678")

    return phone


def validate_order_number(v: str) -> str:
    """Validate order number format"""
    if not v:
        raise ValueError("Order number is required")

    if v == "DEMO":
        return v

    # Expected format: PK-YYMMDD-XXXX
    if not re.match(r'^PK-\d{6}-[A-Z0-9]{4}$', v):
        raise ValueError("Invalid order number format")

    return v


# Annotated types for reuse
KenyanPhone = Annotated[str, BeforeValidator(validate_kenyan_phone)]
OrderNumber = Annotated[str, BeforeValidator(validate_order_number)]

# Valid delivery cities
DeliveryCity = Literal[
    "nairobi_cbd", "nairobi", "thika", "nakuru",
    "mombasa", "kisumu", "eldoret", "other"
]


class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    field: str | None = None
    message: str | None = None


class SuccessResponse(BaseModel):
    """Standard success response"""
    success: bool = True
    message: str | None = None
