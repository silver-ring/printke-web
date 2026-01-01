#!/usr/bin/env python3
"""
PrintKe Full Flow Test Script
Tests: Order Creation → Payment → Auto-Print → Status Check

IMPORTANT: Printing is in MOCK MODE - no real printing occurs
"""
import requests
import time
import sys
from PIL import Image, ImageDraw, ImageFont
import io
import os

BASE_URL = "http://localhost:8000"

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

def print_header(text):
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}  {text}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")

def print_success(text):
    print(f"{GREEN}✓ {text}{RESET}")

def print_error(text):
    print(f"{RED}✗ {text}{RESET}")

def print_info(text):
    print(f"{YELLOW}→ {text}{RESET}")

def create_test_card_image():
    """Create a sample ID card image for testing"""
    # CR80 card dimensions at 300 DPI (3.375" x 2.125")
    width, height = 1012, 638

    # Create card with gradient background
    img = Image.new('RGB', (width, height), color='#1a5276')
    draw = ImageDraw.Draw(img)

    # White content area
    margin = 30
    draw.rectangle([margin, margin, width-margin, height-margin], fill='white', outline='#1a5276', width=3)

    # Company header
    draw.rectangle([margin, margin, width-margin, 100], fill='#1a5276')

    # Add text (using default font)
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except:
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large

    # Header text
    draw.text((width//2, 65), "PRINTKE TEST CARD", fill='white', font=font_large, anchor='mm')

    # Employee info
    draw.text((200, 160), "Name:", fill='#333', font=font_medium)
    draw.text((200, 195), "John Kamau Mwangi", fill='#1a5276', font=font_large)

    draw.text((200, 270), "Department:", fill='#333', font=font_medium)
    draw.text((200, 305), "Software Engineering", fill='#1a5276', font=font_medium)

    draw.text((200, 370), "Employee ID:", fill='#333', font=font_medium)
    draw.text((200, 405), "PKE-2024-001", fill='#1a5276', font=font_medium)

    # Photo placeholder
    draw.rectangle([750, 130, 950, 380], fill='#ecf0f1', outline='#bdc3c7', width=2)
    draw.text((850, 255), "PHOTO", fill='#7f8c8d', font=font_medium, anchor='mm')

    # Footer
    draw.text((width//2, height-50), "Valid: 2024 - 2025", fill='#666', font=font_small, anchor='mm')

    # Save to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)

    return img_bytes

def test_health_check():
    """Test 1: Health Check"""
    print_info("Testing health endpoint...")

    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        data = response.json()

        if response.status_code == 200 and data.get('status') == 'healthy':
            print_success(f"Server is healthy")
            print_success(f"Mock Mode: {data.get('mock_mode', 'Unknown')}")

            if not data.get('mock_mode'):
                print_error("WARNING: Mock mode is OFF! Real printing may occur!")
                return False
            return True
        else:
            print_error(f"Health check failed: {data}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to server. Is it running on port 8000?")
        return False

def test_pricing():
    """Test 2: Pricing Calculation"""
    print_info("Testing pricing calculation...")

    # Pricing tiers:
    # 1-10: KES 400, 11-50: KES 300, 51-200: KES 200
    # 201-500: KES 150, 501-1000: KES 120, 1001+: KES 100
    test_cases = [
        {"quantity": 1, "city": "nairobi", "expected_unit": 400},
        {"quantity": 10, "city": "nairobi", "expected_unit": 400},
        {"quantity": 50, "city": "mombasa", "expected_unit": 300},
        {"quantity": 100, "city": "kisumu", "expected_unit": 200},
    ]

    all_passed = True
    for case in test_cases:
        response = requests.post(
            f"{BASE_URL}/api/orders/calculate",
            json={"quantity": case["quantity"], "delivery_city": case["city"]}
        )
        data = response.json()

        if data.get("unit_price") == case["expected_unit"]:
            print_success(f"Qty {case['quantity']:3d} @ KES {data['unit_price']:.0f}/card = KES {data['total']:,.0f} (delivery to {case['city']})")
        else:
            print_error(f"Qty {case['quantity']}: Expected {case['expected_unit']}, got {data.get('unit_price')}")
            all_passed = False

    return all_passed

def test_create_order():
    """Test 3: Create Order with Image Upload"""
    print_info("Creating test order...")

    # Create test card image
    card_image = create_test_card_image()

    # Order details
    order_data = {
        "name": "Jane Wanjiku Njeri",
        "phone": "0722456789",
        "email": "jane.wanjiku@example.com",
        "delivery_address": "45 Kenyatta Avenue, CBD, Near Archives Building, Nairobi",
        "delivery_city": "nairobi",
        "quantity": 25
    }

    files = {
        "front": ("test_card.png", card_image, "image/png")
    }

    response = requests.post(
        f"{BASE_URL}/api/orders/create",
        data=order_data,
        files=files
    )

    if response.status_code == 201:
        data = response.json()
        print_success(f"Order created: {data['order_number']}")
        print_success(f"Quantity: {data['quantity']} cards")
        print_success(f"Unit Price: KES {data['unit_price']:.0f}")
        print_success(f"Subtotal: KES {data['subtotal']:,.0f}")
        print_success(f"Delivery: KES {data['delivery_fee']:,.0f}")
        print_success(f"Total: KES {data['total']:,.0f}")
        return data['order_number']
    else:
        print_error(f"Failed to create order: {response.text}")
        return None

def test_get_order(order_number):
    """Test 4: Get Order Details"""
    print_info(f"Fetching order {order_number}...")

    response = requests.get(f"{BASE_URL}/api/orders/{order_number}")

    if response.status_code == 200:
        data = response.json()
        print_success(f"Order Status: {data['status']}")
        print_success(f"Payment Status: {data['payment_status']}")
        print_success(f"Delivery: {data['delivery_city']} - {data['delivery_address'][:50]}...")
        return True
    else:
        print_error(f"Failed to get order: {response.text}")
        return False

def test_pdf_preview(order_number):
    """Test 5: PDF Preview"""
    print_info(f"Testing PDF preview for {order_number}...")

    response = requests.get(f"{BASE_URL}/api/orders/{order_number}/preview")

    if response.status_code == 200 and response.headers.get('content-type') == 'application/pdf':
        print_success(f"PDF generated successfully ({len(response.content):,} bytes)")

        # Save PDF for inspection
        pdf_path = f"/tmp/printke_test_{order_number}.pdf"
        with open(pdf_path, 'wb') as f:
            f.write(response.content)
        print_success(f"PDF saved to: {pdf_path}")
        return True
    else:
        print_error(f"PDF preview failed: {response.status_code}")
        return False

def test_payment(order_number):
    """Test 6: Mock M-Pesa Payment"""
    print_info(f"Initiating M-Pesa payment for {order_number}...")

    response = requests.post(
        f"{BASE_URL}/api/payments/mpesa/initiate",
        json={
            "order_number": order_number,
            "phone": "0722456789"
        }
    )

    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            print_success(f"Payment successful (MOCK MODE)")
            print_success(f"Receipt: {data.get('receipt', 'N/A')}")
            print_success(f"Auto-printed: {data.get('auto_printed', False)}")
            return True
        else:
            print_error(f"Payment failed: {data}")
            return False
    else:
        print_error(f"Payment request failed: {response.text}")
        return False

def test_order_after_payment(order_number):
    """Test 7: Verify Order Status After Payment"""
    print_info(f"Verifying order status after payment...")

    response = requests.get(f"{BASE_URL}/api/orders/{order_number}")

    if response.status_code == 200:
        data = response.json()

        checks = [
            ("Payment Status", data['payment_status'], "paid"),
            ("Order Status", data['status'], "printed"),  # In mock mode, goes straight to printed
        ]

        all_passed = True
        for name, actual, expected in checks:
            if actual == expected:
                print_success(f"{name}: {actual}")
            else:
                print_error(f"{name}: Expected '{expected}', got '{actual}'")
                all_passed = False

        if data.get('paid_at'):
            print_success(f"Paid at: {data['paid_at']}")
        if data.get('printed_at'):
            print_success(f"Printed at: {data['printed_at']}")

        return all_passed
    else:
        print_error(f"Failed to get order: {response.text}")
        return False

def test_admin_login():
    """Test 8: Admin Authentication"""
    print_info("Testing admin login...")

    response = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={
            "email": "admin@printke.co.ke",
            "password": "admin123"
        }
    )

    if response.status_code == 200:
        data = response.json()
        print_success(f"Admin login successful")
        print_success(f"User: {data['user']['name']} ({data['user']['email']})")
        return data['access_token']
    else:
        print_error(f"Admin login failed: {response.text}")
        return None

def test_admin_dashboard(token):
    """Test 9: Admin Dashboard"""
    print_info("Testing admin dashboard...")

    response = requests.get(
        f"{BASE_URL}/api/admin/dashboard",
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code == 200:
        data = response.json()
        print_success(f"Total Orders: {data['orders']['total']}")
        print_success(f"Today's Orders: {data['orders']['today']}")
        print_success(f"Total Revenue: KES {data['revenue']['total']:,.0f}")
        print_success(f"Today's Revenue: KES {data['revenue']['today']:,.0f}")
        print_success(f"Cards Printed: {data['cards_printed']}")
        return True
    else:
        print_error(f"Dashboard failed: {response.text}")
        return False

def main():
    print_header("PRINTKE FULL FLOW TEST")
    print(f"{YELLOW}Testing complete order flow with MOCK PRINTING{RESET}\n")

    results = {}

    # Test 1: Health Check
    print_header("TEST 1: Health Check")
    results['health'] = test_health_check()
    if not results['health']:
        print_error("\nServer not ready. Aborting tests.")
        sys.exit(1)

    # Test 2: Pricing
    print_header("TEST 2: Pricing Calculation")
    results['pricing'] = test_pricing()

    # Test 3: Create Order
    print_header("TEST 3: Create Order")
    order_number = test_create_order()
    results['create_order'] = order_number is not None

    if not order_number:
        print_error("\nCannot continue without order. Aborting.")
        sys.exit(1)

    # Test 4: Get Order
    print_header("TEST 4: Get Order Details")
    results['get_order'] = test_get_order(order_number)

    # Test 5: PDF Preview
    print_header("TEST 5: PDF Preview")
    results['pdf_preview'] = test_pdf_preview(order_number)

    # Test 6: Payment
    print_header("TEST 6: M-Pesa Payment (MOCK)")
    results['payment'] = test_payment(order_number)

    # Test 7: Verify After Payment
    print_header("TEST 7: Verify Order After Payment")
    results['after_payment'] = test_order_after_payment(order_number)

    # Test 8: Admin Login
    print_header("TEST 8: Admin Login")
    token = test_admin_login()
    results['admin_login'] = token is not None

    # Test 9: Admin Dashboard
    if token:
        print_header("TEST 9: Admin Dashboard")
        results['admin_dashboard'] = test_admin_dashboard(token)

    # Summary
    print_header("TEST SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"  {test_name.replace('_', ' ').title():.<40} {status}")

    print(f"\n{BOLD}Results: {passed}/{total} tests passed{RESET}")

    if passed == total:
        print(f"\n{GREEN}{BOLD}All tests passed! PrintKe is ready.{RESET}")
        print(f"\n{YELLOW}Order Number: {order_number}{RESET}")
        print(f"{YELLOW}Track at: {BASE_URL}/track/{order_number}{RESET}")
    else:
        print(f"\n{RED}{BOLD}Some tests failed. Please check the errors above.{RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()
