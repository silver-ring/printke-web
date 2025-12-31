"""
Admin API Routes
"""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta

from src.models import db, Order, OrderItem, User, Payment, PrintJob, ContactMessage
from src.services.card_processor import PrintService

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/dashboard', methods=['GET'])
def dashboard():
    """Get dashboard statistics"""
    # Get date ranges
    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Order statistics
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    processing_orders = Order.query.filter(Order.status.in_(['paid', 'processing', 'printing'])).count()
    completed_orders = Order.query.filter_by(status='delivered').count()

    # Today's orders
    today_orders = Order.query.filter(
        db.func.date(Order.created_at) == today
    ).count()

    # Revenue
    total_revenue = db.session.query(
        db.func.sum(Order.total)
    ).filter(Order.payment_status == 'paid').scalar() or 0

    today_revenue = db.session.query(
        db.func.sum(Order.total)
    ).filter(
        Order.payment_status == 'paid',
        db.func.date(Order.paid_at) == today
    ).scalar() or 0

    month_revenue = db.session.query(
        db.func.sum(Order.total)
    ).filter(
        Order.payment_status == 'paid',
        Order.paid_at >= datetime.combine(month_ago, datetime.min.time())
    ).scalar() or 0

    # Cards printed
    total_cards = db.session.query(
        db.func.sum(OrderItem.quantity)
    ).join(Order).filter(
        Order.status.in_(['printed', 'shipped', 'delivered'])
    ).scalar() or 0

    # Recent orders
    recent_orders = Order.query.order_by(
        Order.created_at.desc()
    ).limit(10).all()

    return jsonify({
        'orders': {
            'total': total_orders,
            'pending': pending_orders,
            'processing': processing_orders,
            'completed': completed_orders,
            'today': today_orders
        },
        'revenue': {
            'total': total_revenue,
            'today': today_revenue,
            'month': month_revenue
        },
        'cards_printed': total_cards,
        'recent_orders': [{
            'order_number': o.order_number,
            'customer': o.guest_name or (o.customer.full_name if o.customer else 'Guest'),
            'total': o.total,
            'status': o.status,
            'payment_status': o.payment_status,
            'created_at': o.created_at.isoformat()
        } for o in recent_orders]
    })


@admin_bp.route('/orders', methods=['GET'])
def list_orders():
    """List all orders with filtering and pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    payment_status = request.args.get('payment_status')
    search = request.args.get('search')

    query = Order.query

    if status:
        query = query.filter_by(status=status)
    if payment_status:
        query = query.filter_by(payment_status=payment_status)
    if search:
        query = query.filter(
            db.or_(
                Order.order_number.ilike(f'%{search}%'),
                Order.guest_name.ilike(f'%{search}%'),
                Order.guest_phone.ilike(f'%{search}%'),
                Order.guest_email.ilike(f'%{search}%')
            )
        )

    query = query.order_by(Order.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page)

    return jsonify({
        'orders': [{
            'order_number': o.order_number,
            'customer': o.guest_name or (o.customer.full_name if o.customer else 'Guest'),
            'phone': o.guest_phone or (o.customer.phone if o.customer else ''),
            'email': o.guest_email or (o.customer.email if o.customer else ''),
            'items_count': o.items.count(),
            'total': o.total,
            'status': o.status,
            'payment_status': o.payment_status,
            'delivery_method': o.delivery_method,
            'delivery_city': o.delivery_city,
            'created_at': o.created_at.isoformat()
        } for o in pagination.items],
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
    })


@admin_bp.route('/orders/<order_number>', methods=['GET'])
def get_order_detail(order_number):
    """Get detailed order information"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    items = [{
        'id': item.id,
        'quantity': item.quantity,
        'unit_price': item.unit_price,
        'total_price': item.total_price,
        'status': item.status,
        'printed_count': item.printed_count,
        'has_front': bool(item.front_image_processed),
        'has_back': bool(item.back_image_processed),
        'has_pdf': bool(item.pdf_file)
    } for item in order.items]

    payments = [{
        'transaction_id': p.transaction_id,
        'method': p.payment_method,
        'amount': p.amount,
        'status': p.status,
        'receipt': p.mpesa_receipt,
        'created_at': p.created_at.isoformat()
    } for p in order.payments]

    return jsonify({
        'order_number': order.order_number,
        'customer': {
            'name': order.guest_name or (order.customer.full_name if order.customer else ''),
            'email': order.guest_email or (order.customer.email if order.customer else ''),
            'phone': order.guest_phone or (order.customer.phone if order.customer else '')
        },
        'status': order.status,
        'payment_status': order.payment_status,
        'subtotal': order.subtotal,
        'delivery_fee': order.delivery_fee,
        'discount': order.discount,
        'total': order.total,
        'delivery': {
            'method': order.delivery_method,
            'address': order.delivery_address,
            'city': order.delivery_city,
            'notes': order.delivery_notes,
            'tracking': order.tracking_number
        },
        'items': items,
        'payments': payments,
        'timestamps': {
            'created': order.created_at.isoformat(),
            'paid': order.paid_at.isoformat() if order.paid_at else None,
            'printed': order.printed_at.isoformat() if order.printed_at else None,
            'shipped': order.shipped_at.isoformat() if order.shipped_at else None,
            'delivered': order.delivered_at.isoformat() if order.delivered_at else None
        }
    })


@admin_bp.route('/orders/<order_number>/status', methods=['PUT'])
def update_order_status(order_number):
    """Update order status"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    data = request.get_json()
    new_status = data.get('status')
    tracking_number = data.get('tracking_number')
    notes = data.get('notes')

    valid_statuses = ['pending', 'paid', 'processing', 'printing', 'printed', 'shipped', 'delivered', 'cancelled']
    if new_status and new_status not in valid_statuses:
        return jsonify({'error': f'Invalid status. Valid: {valid_statuses}'}), 400

    if new_status:
        order.status = new_status

        # Update timestamps
        if new_status == 'printed':
            order.printed_at = datetime.utcnow()
        elif new_status == 'shipped':
            order.shipped_at = datetime.utcnow()
        elif new_status == 'delivered':
            order.delivered_at = datetime.utcnow()

    if tracking_number:
        order.tracking_number = tracking_number

    if notes:
        order.delivery_notes = notes

    db.session.commit()

    return jsonify({
        'success': True,
        'order_number': order.order_number,
        'status': order.status
    })


@admin_bp.route('/orders/<order_number>/print', methods=['POST'])
def print_order(order_number):
    """Send order to printer"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    item = order.items.first()
    if not item or not item.pdf_file:
        return jsonify({'error': 'No PDF available'}), 400

    printer = PrintService(
        printer_name=current_app.config.get('PRINTER_NAME', 'LXM-Card-Printer'),
        mock_mode=current_app.config.get('MOCK_PRINTING', True)
    )

    result = printer.print_card(item.pdf_file, copies=item.quantity)

    if result['success']:
        order.status = 'printing'
        item.status = 'printing'

        # Create print job record
        print_job = PrintJob(
            order_item_id=item.id,
            job_id=result.get('job_id'),
            copies=item.quantity,
            status='printing' if not result.get('mock') else 'completed'
        )
        db.session.add(print_job)
        db.session.commit()

    return jsonify(result)


@admin_bp.route('/print-queue', methods=['GET'])
def get_print_queue():
    """Get print queue status"""
    jobs = PrintJob.query.filter(
        PrintJob.status.in_(['queued', 'printing'])
    ).order_by(PrintJob.created_at).all()

    return jsonify({
        'queue': [{
            'id': job.id,
            'order_number': job.order_item.order.order_number,
            'copies': job.copies,
            'status': job.status,
            'created_at': job.created_at.isoformat()
        } for job in jobs]
    })


@admin_bp.route('/messages', methods=['GET'])
def list_messages():
    """List contact messages"""
    page = request.args.get('page', 1, type=int)
    unread_only = request.args.get('unread', 'false').lower() == 'true'

    query = ContactMessage.query
    if unread_only:
        query = query.filter_by(is_read=False)

    query = query.order_by(ContactMessage.created_at.desc())
    pagination = query.paginate(page=page, per_page=20)

    return jsonify({
        'messages': [{
            'id': m.id,
            'name': m.name,
            'email': m.email,
            'phone': m.phone,
            'subject': m.subject,
            'message': m.message,
            'is_read': m.is_read,
            'created_at': m.created_at.isoformat()
        } for m in pagination.items],
        'pagination': {
            'page': pagination.page,
            'total': pagination.total,
            'pages': pagination.pages
        },
        'unread_count': ContactMessage.query.filter_by(is_read=False).count()
    })


@admin_bp.route('/messages/<int:message_id>/read', methods=['PUT'])
def mark_message_read(message_id):
    """Mark message as read"""
    message = ContactMessage.query.get(message_id)
    if not message:
        return jsonify({'error': 'Message not found'}), 404

    message.is_read = True
    db.session.commit()

    return jsonify({'success': True})
