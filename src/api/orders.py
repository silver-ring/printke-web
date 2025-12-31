"""
Order Management API Routes
"""
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime

from src.models import db, Order, OrderItem, User, Product
from src.services.card_processor import CardProcessor, PrintService

orders_bp = Blueprint('orders', __name__, url_prefix='/api/orders')


def allowed_file(filename):
    """Check if file extension is allowed"""
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def get_price_per_card(quantity):
    """Calculate price per card based on quantity tier"""
    tiers = current_app.config.get('PRICING_TIERS', {
        'single': {'min': 1, 'max': 50, 'price': 300},
        'small': {'min': 51, 'max': 200, 'price': 200},
        'medium': {'min': 201, 'max': 500, 'price': 150},
        'large': {'min': 501, 'max': 1000, 'price': 120},
        'bulk': {'min': 1001, 'max': 999999, 'price': 100},
    })

    for tier in tiers.values():
        if tier['min'] <= quantity <= tier['max']:
            return tier['price']
    return 300  # Default price


@orders_bp.route('/create', methods=['POST'])
def create_order():
    """
    Create a new order with card images

    Expects multipart/form-data with:
    - front: Front image file
    - back: Back image file (optional for single-sided)
    - quantity: Number of cards
    - name: Customer name
    - email: Customer email
    - phone: Customer phone
    - delivery_method: 'delivery' or 'pickup'
    - delivery_address: Address for delivery
    - delivery_city: City for delivery fee calculation
    """
    try:
        # Validate files
        if 'front' not in request.files:
            return jsonify({'error': 'Front image is required'}), 400

        front_file = request.files['front']
        back_file = request.files.get('back')

        if front_file.filename == '':
            return jsonify({'error': 'No front image selected'}), 400

        if not allowed_file(front_file.filename):
            return jsonify({'error': 'Invalid file type. Use PNG, JPG, or JPEG'}), 400

        if back_file and back_file.filename and not allowed_file(back_file.filename):
            return jsonify({'error': 'Invalid back image file type'}), 400

        # Get form data
        quantity = int(request.form.get('quantity', 1))
        name = request.form.get('name', '')
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')
        delivery_method = request.form.get('delivery_method', 'delivery')
        delivery_address = request.form.get('delivery_address', '')
        delivery_city = request.form.get('delivery_city', 'nairobi')

        # Generate order number
        order_number = Order.generate_order_number()
        order_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], order_number)
        os.makedirs(order_folder, exist_ok=True)

        # Save original files
        front_orig = os.path.join(order_folder, 'front_original.png')
        front_file.save(front_orig)

        back_orig = None
        if back_file and back_file.filename:
            back_orig = os.path.join(order_folder, 'back_original.png')
            back_file.save(back_orig)

        # Process images
        processor = CardProcessor(
            current_app.config['UPLOAD_FOLDER'],
            os.path.join(current_app.config['UPLOAD_FOLDER'], 'processed')
        )

        front_processed = os.path.join(order_folder, 'front_card.png')
        processor.resize_image(front_orig, front_processed)

        back_processed = None
        pdf_path = os.path.join(order_folder, f'{order_number}.pdf')

        if back_orig:
            back_processed = os.path.join(order_folder, 'back_card.png')
            processor.resize_image(back_orig, back_processed)
            processor.create_card_pdf(front_processed, back_processed, pdf_path)
        else:
            processor.create_single_side_pdf(front_processed, pdf_path)

        # Calculate pricing
        unit_price = get_price_per_card(quantity)
        subtotal = unit_price * quantity

        delivery_fees = current_app.config.get('DELIVERY_FEES', {})
        delivery_fee = delivery_fees.get(delivery_city.lower(), delivery_fees.get('other', 800))
        if delivery_method == 'pickup':
            delivery_fee = 0

        total = subtotal + delivery_fee

        # Create order in database
        order = Order(
            order_number=order_number,
            guest_name=name,
            guest_email=email,
            guest_phone=phone,
            status='pending',
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            total=total,
            delivery_method=delivery_method,
            delivery_address=delivery_address,
            delivery_city=delivery_city
        )
        db.session.add(order)
        db.session.flush()

        # Create order item
        order_item = OrderItem(
            order_id=order.id,
            quantity=quantity,
            unit_price=unit_price,
            total_price=subtotal,
            front_image_original=front_orig,
            back_image_original=back_orig,
            front_image_processed=front_processed,
            back_image_processed=back_processed,
            pdf_file=pdf_path
        )
        db.session.add(order_item)
        db.session.commit()

        return jsonify({
            'success': True,
            'order_number': order_number,
            'quantity': quantity,
            'unit_price': unit_price,
            'subtotal': subtotal,
            'delivery_fee': delivery_fee,
            'total': total,
            'preview_url': f'/api/orders/{order_number}/preview',
            'message': 'Order created successfully'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Order creation error: {e}")
        return jsonify({'error': str(e)}), 500


@orders_bp.route('/<order_number>', methods=['GET'])
def get_order(order_number):
    """Get order details"""
    from datetime import timedelta

    # Handle DEMO order for testing tracking
    if order_number == 'DEMO':
        shipped_time = datetime.utcnow() - timedelta(minutes=10)
        return jsonify({
            'order_number': 'DEMO',
            'status': 'shipped',
            'payment_status': 'paid',
            'subtotal': 2000,
            'delivery_fee': 300,
            'discount': 0,
            'total': 2300,
            'delivery_method': 'delivery',
            'delivery_city': 'nairobi_cbd',
            'delivery_address': 'Kenyatta Avenue, Nairobi CBD',
            'tracking_number': 'PKE-DEMO-001',
            'created_at': (shipped_time - timedelta(hours=2)).isoformat(),
            'paid_at': (shipped_time - timedelta(hours=1, minutes=50)).isoformat(),
            'printed_at': (shipped_time - timedelta(minutes=30)).isoformat(),
            'shipped_at': shipped_time.isoformat(),
            'delivered_at': None,
            'items': [{'quantity': 5, 'unit_price': 400, 'total_price': 2000, 'status': 'shipped'}]
        })

    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    items = []
    for item in order.items:
        items.append({
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'total_price': item.total_price,
            'status': item.status
        })

    return jsonify({
        'order_number': order.order_number,
        'status': order.status,
        'payment_status': order.payment_status,
        'subtotal': order.subtotal,
        'delivery_fee': order.delivery_fee,
        'discount': order.discount,
        'total': order.total,
        'delivery_method': order.delivery_method,
        'delivery_city': order.delivery_city,
        'delivery_address': order.delivery_address,
        'tracking_number': order.tracking_number,
        'created_at': order.created_at.isoformat(),
        'paid_at': order.paid_at.isoformat() if order.paid_at else None,
        'printed_at': order.printed_at.isoformat() if order.printed_at else None,
        'shipped_at': order.shipped_at.isoformat() if order.shipped_at else None,
        'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
        'items': items
    })


@orders_bp.route('/<order_number>/preview', methods=['GET'])
def preview_order(order_number):
    """Get PDF preview for order"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    item = order.items.first()
    if not item or not item.pdf_file:
        return jsonify({'error': 'No PDF available'}), 404

    if not os.path.exists(item.pdf_file):
        return jsonify({'error': 'PDF file not found'}), 404

    return send_file(item.pdf_file, mimetype='application/pdf')


@orders_bp.route('/<order_number>/download', methods=['GET'])
def download_order(order_number):
    """Download PDF for order"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    item = order.items.first()
    if not item or not item.pdf_file:
        return jsonify({'error': 'No PDF available'}), 404

    return send_file(
        item.pdf_file,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'card_{order_number}.pdf'
    )


@orders_bp.route('/<order_number>/card-image/<side>', methods=['GET'])
def get_card_image(order_number, side):
    """Get processed card image (front or back)"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    item = order.items.first()
    if not item:
        return jsonify({'error': 'Order item not found'}), 404

    if side == 'front' and item.front_image_processed:
        return send_file(item.front_image_processed, mimetype='image/png')
    elif side == 'back' and item.back_image_processed:
        return send_file(item.back_image_processed, mimetype='image/png')
    else:
        return jsonify({'error': 'Image not found'}), 404


@orders_bp.route('/<order_number>/print', methods=['POST'])
def print_order(order_number):
    """Send order to printer"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if order.payment_status != 'paid' and not current_app.config.get('MOCK_PRINTING'):
        return jsonify({'error': 'Order must be paid before printing'}), 400

    item = order.items.first()
    if not item or not item.pdf_file:
        return jsonify({'error': 'No PDF available for printing'}), 404

    printer = PrintService(
        printer_name=current_app.config.get('PRINTER_NAME', 'LXM-Card-Printer'),
        mock_mode=current_app.config.get('MOCK_PRINTING', True)
    )

    result = printer.print_card(item.pdf_file, copies=item.quantity)

    if result['success']:
        order.status = 'printing'
        item.status = 'printing'
        db.session.commit()

    return jsonify(result)


@orders_bp.route('/pricing', methods=['GET'])
def get_pricing():
    """Get pricing tiers"""
    tiers = current_app.config.get('PRICING_TIERS', {})
    delivery_fees = current_app.config.get('DELIVERY_FEES', {})

    return jsonify({
        'pricing_tiers': tiers,
        'delivery_fees': delivery_fees
    })


@orders_bp.route('/calculate', methods=['POST'])
def calculate_price():
    """Calculate price for given quantity and delivery"""
    data = request.get_json()
    quantity = int(data.get('quantity', 1))
    delivery_city = data.get('delivery_city', 'nairobi')
    delivery_method = data.get('delivery_method', 'delivery')

    unit_price = get_price_per_card(quantity)
    subtotal = unit_price * quantity

    delivery_fees = current_app.config.get('DELIVERY_FEES', {})
    delivery_fee = delivery_fees.get(delivery_city.lower(), delivery_fees.get('other', 800))
    if delivery_method == 'pickup':
        delivery_fee = 0

    total = subtotal + delivery_fee

    return jsonify({
        'quantity': quantity,
        'unit_price': unit_price,
        'subtotal': subtotal,
        'delivery_fee': delivery_fee,
        'total': total
    })


@orders_bp.route('/demo-tracking', methods=['GET'])
def demo_tracking():
    """
    Demo endpoint for testing tracking page.
    Returns fake order data that simulates a shipped order.
    Use: /track/DEMO to test the tracking page.
    """
    from datetime import timedelta

    # Simulate order shipped 10 minutes ago
    shipped_time = datetime.utcnow() - timedelta(minutes=10)

    return jsonify({
        'order_number': 'DEMO',
        'status': 'shipped',
        'payment_status': 'paid',
        'subtotal': 2000,
        'delivery_fee': 300,
        'discount': 0,
        'total': 2300,
        'delivery_method': 'delivery',
        'delivery_city': 'nairobi_cbd',
        'delivery_address': 'Kenyatta Avenue, Nairobi CBD',
        'tracking_number': 'PKE-DEMO-001',
        'created_at': (shipped_time - timedelta(hours=2)).isoformat(),
        'paid_at': (shipped_time - timedelta(hours=1, minutes=50)).isoformat(),
        'printed_at': (shipped_time - timedelta(minutes=30)).isoformat(),
        'shipped_at': shipped_time.isoformat(),
        'delivered_at': None,
        'items': [{'quantity': 5, 'unit_price': 400, 'total_price': 2000, 'status': 'shipped'}]
    })
