"""
Test WebSocket real-time tracking
"""
import asyncio
import json
import websockets


async def test_websocket_tracking():
    """Test WebSocket connection for delivery tracking"""
    print("\n=== Testing WebSocket Real-Time Tracking ===\n")

    # Test 1: Connect without order_number (admin view)
    print("Test 1: Admin dashboard connection (all updates)")
    try:
        async with websockets.connect("ws://localhost:8000/api/ws/deliveries") as websocket:
            # Receive connection confirmation
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(response)
            print(f"  ✓ Connected: {data['type']}")
            print(f"    Timestamp: {data['timestamp']}")

            # Send ping
            await websocket.send("ping")
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(response)
            print(f"  ✓ Ping response: {data['type']}")

            print("  ✓ Admin WebSocket connection successful\n")
    except Exception as e:
        print(f"  ✗ Admin WebSocket failed: {e}\n")
        return False

    # Test 2: Connect with specific order_number (customer view)
    print("Test 2: Customer tracking connection (specific order)")
    try:
        async with websockets.connect("ws://localhost:8000/api/ws/deliveries?order_number=PK-251231-5067") as websocket:
            # Receive connection confirmation
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(response)
            print(f"  ✓ Connected: {data['type']}")
            print(f"    Order: {data['order_number']}")

            # Receive current status (if delivery exists)
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                data = json.loads(response)
                if data['type'] == 'current_status':
                    print(f"  ✓ Received current status:")
                    print(f"    Delivery ID: {data['delivery_id']}")
                    print(f"    Status: {data['status']}")
                    if 'driver' in data and data['driver']:
                        print(f"    Driver: {data['driver']['name']}")
                        if data['driver']['current_lat']:
                            print(f"    Location: ({data['driver']['current_lat']}, {data['driver']['current_lng']})")
            except asyncio.TimeoutError:
                print("  ℹ No current delivery status available")

            # Send ping
            await websocket.send("ping")
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(response)
            print(f"  ✓ Ping response: {data['type']}")

            print("  ✓ Customer WebSocket connection successful\n")
    except Exception as e:
        print(f"  ✗ Customer WebSocket failed: {e}\n")
        return False

    print("✓ All WebSocket tests passed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_websocket_tracking())
