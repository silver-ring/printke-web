"""
Test script for delivery tracking endpoints
"""
import asyncio
import httpx
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api"
ADMIN_TOKEN = None
DRIVER_TOKEN = None
DRIVER_ID = None
ORDER_NUMBER = None
DELIVERY_ID = None


async def test_admin_login():
    """Test admin login"""
    global ADMIN_TOKEN
    print("\n=== Testing Admin Login ===")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/admin/login",
            json={"email": "admin@printke.co.ke", "password": "admin123"}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            ADMIN_TOKEN = data["access_token"]
            print(f"✓ Admin login successful")
            print(f"  Token: {ADMIN_TOKEN[:20]}...")
            return True
        else:
            print(f"✗ Admin login failed: {response.text}")
            return False


async def test_create_driver():
    """Test creating a new driver or use existing"""
    global DRIVER_ID
    print("\n=== Testing Create Driver ===")

    driver_data = {
        "name": "John Doe",
        "phone": "+254712345678",
        "password": "driver123",
        "vehicle_type": "Motorcycle",
        "vehicle_plate": "KAA 123X"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/admin/drivers",
            json=driver_data,
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            DRIVER_ID = data["id"]
            print(f"✓ Driver created successfully")
            print(f"  ID: {data['id']}")
            print(f"  Name: {data['name']}")
            print(f"  Phone: {data['phone']}")
            print(f"  Vehicle: {data['vehicle_type']} - {data['vehicle_plate']}")
            return True
        elif response.status_code == 400 and "already exists" in response.text:
            # Driver already exists, get it from the list
            list_response = await client.get(
                f"{BASE_URL}/admin/drivers",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
            )
            if list_response.status_code == 200:
                drivers = list_response.json()["drivers"]
                for driver in drivers:
                    if driver["phone"] == driver_data["phone"]:
                        DRIVER_ID = driver["id"]
                        print(f"✓ Driver already exists, using existing driver")
                        print(f"  ID: {driver['id']}")
                        print(f"  Name: {driver['name']}")
                        return True
            print(f"✗ Could not find existing driver")
            return False
        else:
            print(f"✗ Create driver failed: {response.text}")
            return False


async def test_list_drivers():
    """Test listing all drivers"""
    print("\n=== Testing List Drivers ===")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/admin/drivers",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Retrieved {data['total']} driver(s)")
            for driver in data['drivers']:
                print(f"  - {driver['name']} ({driver['phone']}) - {driver['vehicle_type']}")
            return True
        else:
            print(f"✗ List drivers failed: {response.text}")
            return False


async def test_driver_login():
    """Test driver login"""
    global DRIVER_TOKEN
    print("\n=== Testing Driver Login ===")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/drivers/login",
            json={"phone": "+254712345678", "password": "driver123"}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            DRIVER_TOKEN = data["access_token"]
            print(f"✓ Driver login successful")
            print(f"  Token: {DRIVER_TOKEN[:20]}...")
            print(f"  Driver: {data['driver']['name']}")
            return True
        else:
            print(f"✗ Driver login failed: {response.text}")
            return False


async def test_create_test_order():
    """Use an existing order for delivery tracking"""
    global ORDER_NUMBER
    print("\n=== Using Existing Order ===")

    # Use existing order
    ORDER_NUMBER = "PK-251231-5067"  # Using an existing printed order

    async with httpx.AsyncClient() as client:
        # Update order status to paid/printed if needed
        update_response = await client.put(
            f"{BASE_URL}/admin/orders/{ORDER_NUMBER}/status",
            json={"status": "printed"},
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )

        if update_response.status_code == 200:
            print(f"✓ Using existing order: {ORDER_NUMBER}")
            print(f"  ✓ Order marked as printed (ready for delivery)")
            return True
        else:
            print(f"✗ Update order failed: {update_response.text}")
            return False


async def test_assign_order_to_driver():
    """Test assigning an order to a driver"""
    global DELIVERY_ID
    print("\n=== Testing Assign Order to Driver ===")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/admin/orders/{ORDER_NUMBER}/assign",
            json={"driver_id": DRIVER_ID},
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            DELIVERY_ID = data["delivery_id"]
            print(f"✓ Order assigned to driver")
            print(f"  Delivery ID: {data['delivery_id']}")
            print(f"  Order: {data['order_number']}")
            print(f"  Driver: {data['driver_name']}")
            print(f"  Status: {data['status']}")
            return True
        else:
            print(f"✗ Assign order failed: {response.text}")
            return False


async def test_get_driver_deliveries():
    """Test getting driver's assigned deliveries"""
    print("\n=== Testing Get Driver Deliveries ===")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/drivers/deliveries",
            headers={"Authorization": f"Bearer {DRIVER_TOKEN}"}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Retrieved {len(data)} delivery(ies)")
            for delivery in data:
                print(f"  - Delivery #{delivery['id']}: Order {delivery['order_id']} - {delivery['status']}")
            return True
        else:
            print(f"✗ Get deliveries failed: {response.text}")
            return False


async def test_start_delivery():
    """Test starting a delivery"""
    print("\n=== Testing Start Delivery ===")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/drivers/deliveries/{DELIVERY_ID}/start",
            headers={"Authorization": f"Bearer {DRIVER_TOKEN}"}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Delivery started")
            print(f"  Delivery ID: {data['delivery_id']}")
            print(f"  Status: {data['status']}")
            print(f"  Started at: {data['started_at']}")
            return True
        else:
            print(f"✗ Start delivery failed: {response.text}")
            return False


async def test_update_location():
    """Test updating delivery location"""
    print("\n=== Testing Update Location ===")

    locations = [
        {"lat": -1.2921, "lng": 36.8219, "accuracy": 10.0, "speed": 30.0},  # Nairobi
        {"lat": -1.2850, "lng": 36.8200, "accuracy": 8.0, "speed": 25.0},
        {"lat": -1.2800, "lng": 36.8180, "accuracy": 12.0, "speed": 20.0},
    ]

    async with httpx.AsyncClient() as client:
        for i, location in enumerate(locations, 1):
            response = await client.post(
                f"{BASE_URL}/drivers/deliveries/{DELIVERY_ID}/location",
                json=location,
                headers={"Authorization": f"Bearer {DRIVER_TOKEN}"}
            )

            if response.status_code == 200:
                data = response.json()
                print(f"  ✓ Location update {i}: ({location['lat']}, {location['lng']}) at {data['location']['timestamp']}")
            else:
                print(f"  ✗ Location update {i} failed: {response.text}")
                return False

            # Small delay between updates
            await asyncio.sleep(0.5)

    print(f"✓ All location updates successful")
    return True


async def test_get_active_deliveries():
    """Test getting all active deliveries (admin)"""
    print("\n=== Testing Get Active Deliveries ===")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/admin/deliveries/active",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Retrieved {data['total']} active delivery(ies)")
            for delivery in data['deliveries']:
                print(f"  - Order {delivery['order_number']}: {delivery['customer_name']}")
                print(f"    Driver: {delivery['driver_name']} ({delivery['driver_phone']})")
                print(f"    Status: {delivery['status']}")
                if delivery['current_lat'] and delivery['current_lng']:
                    print(f"    Location: ({delivery['current_lat']}, {delivery['current_lng']})")
                    print(f"    Last update: {delivery['last_location_update']}")
            return True
        else:
            print(f"✗ Get active deliveries failed: {response.text}")
            return False


async def test_complete_delivery():
    """Test completing a delivery"""
    print("\n=== Testing Complete Delivery ===")

    completion_data = {
        "notes": "Package delivered successfully to customer",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/drivers/deliveries/{DELIVERY_ID}/complete",
            json=completion_data,
            headers={"Authorization": f"Bearer {DRIVER_TOKEN}"}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Delivery completed")
            print(f"  Delivery ID: {data['delivery_id']}")
            print(f"  Order: {data['order_number']}")
            print(f"  Status: {data['status']}")
            print(f"  Delivered at: {data['delivered_at']}")
            return True
        else:
            print(f"✗ Complete delivery failed: {response.text}")
            return False


async def test_update_driver():
    """Test updating driver information"""
    print("\n=== Testing Update Driver ===")

    update_data = {
        "vehicle_type": "Van",
        "vehicle_plate": "KBB 456Y"
    }

    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{BASE_URL}/admin/drivers/{DRIVER_ID}",
            json=update_data,
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Driver updated")
            print(f"  Name: {data['name']}")
            print(f"  Vehicle: {data['vehicle_type']} - {data['vehicle_plate']}")
            return True
        else:
            print(f"✗ Update driver failed: {response.text}")
            return False


async def main():
    """Run all tests"""
    print("=" * 60)
    print("DELIVERY TRACKING SYSTEM - ENDPOINT TESTS")
    print("=" * 60)

    tests = [
        ("Admin Login", test_admin_login),
        ("Create Driver", test_create_driver),
        ("List Drivers", test_list_drivers),
        ("Driver Login", test_driver_login),
        ("Use Existing Order", test_create_test_order),
        ("Assign Order to Driver", test_assign_order_to_driver),
        ("Get Driver Deliveries", test_get_driver_deliveries),
        ("Start Delivery", test_start_delivery),
        ("Update Location (3x)", test_update_location),
        ("Get Active Deliveries", test_get_active_deliveries),
        ("Complete Delivery", test_complete_delivery),
        ("Update Driver", test_update_driver),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n✗ {test_name} raised exception: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
