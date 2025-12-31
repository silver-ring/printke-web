"""
Admin API Routes
Production-ready with authentication and authorization
"""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user, login_user, logout_user
from functools import wraps
from datetime import datetime, timedelta

from src.models import db, Order, OrderItem, User, Payment, PrintJob, ContactMessage
from src.services.card_processor import PrintService
from src.utils.validators import ValidationError, validate_email, sanitize_string

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/login', methods=['POST'])
def admin_login():
    """Admin login endpoint"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'JSON payload required'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        current_app.logger.warning(f"Failed login attempt for: {email}")
        return jsonify({'error': 'Invalid email or password'}), 401

    if not user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403

    login_user(user)
    current_app.logger.info(f"Admin login: {email}")

    return jsonify({
        'success': True,
        'user': {
            'email': user.email,
            'name': user.full_name
        }
    })


@admin_bp.route('/logout', methods=['POST'])
@login_required
def admin_logout():
    """Admin logout endpoint"""
    logout_user()
    return jsonify({'success': True})


@admin_bp.route('/me', methods=['GET'])
@login_required
@admin_required
def get_current_admin():
    """Get current admin user info"""
    return jsonify({
        'email': current_user.email,
        'name': current_user.full_name,
        'is_admin': current_user.is_admin
    })


@admin_bp.route('/dashboard', methods=['GET'])
@login_required
@admin_required
def dashboard():
    """Get dashboard statistics"""
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
            'total': float(total_revenue),
            'today': float(today_revenue),
            'month': float(month_revenue),
            'currency': 'KES'
        },
        'cards_printed': total_cards or 0,
        'recent_orders': [{
            'order_number': o.order_number,
            'customer': o.guest_name or (o.customer.full_name if o.customer else 'Guest'),
            'total': float(o.total),
            'status': o.status,
            'payment_status': o.payment_status,
            'created_at': o.created_at.isoformat()
        } for o in recent_orders]
    })


@admin_bp.route('/orders', methods=['GET'])
@login_required
@admin_required
def list_orders():
    """List all orders with filtering and pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)  # Max 100 per page
    status = request.args.get('status')
    payment_status = request.args.get('payment_status')
    search = request.args.get('search', '').strip()

    query = Order.query

    if status:
        query = query.filter_by(status=status)
    if payment_status:
        query = query.filter_by(payment_status=payment_status)
    if search:
        # Sanitize search input
        search = sanitize_string(search, max_length=100)
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
            'total': float(o.total),
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
@login_required
@admin_required
def get_order_detail(order_number):
    """Get detailed order information"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    items = [{
        'id': item.id,
        'quantity': item.quantity,
        'unit_price': float(item.unit_price),
        'total_price': float(item.total_price),
        'status': item.status,
        'printed_count': item.printed_count,
        'has_front': bool(item.front_image_processed),
        'has_back': bool(item.back_image_processed),
        'has_pdf': bool(item.pdf_file)
    } for item in order.items]

    payments = [{
        'transaction_id': p.transaction_id,
        'method': p.payment_method,
        'amount': float(p.amount),
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
        'subtotal': float(order.subtotal),
        'delivery_fee': float(order.delivery_fee),
        'discount': float(order.discount),
        'total': float(order.total),
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
@login_required
@admin_required
def update_order_status(order_number):
    """Update order status"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON payload required'}), 400

    new_status = data.get('status')
    tracking_number = data.get('tracking_number')
    notes = data.get('notes')

    valid_statuses = ['pending', 'paid', 'processing', 'printing', 'printed', 'shipped', 'delivered', 'cancelled']
    if new_status and new_status not in valid_statuses:
        return jsonify({'error': f'Invalid status. Valid: {valid_statuses}'}), 400

    old_status = order.status

    if new_status:
        order.status = new_status

        # Update timestamps
        if new_status == 'printed' and not order.printed_at:
            order.printed_at = datetime.utcnow()
        elif new_status == 'shipped' and not order.shipped_at:
            order.shipped_at = datetime.utcnow()
        elif new_status == 'delivered' and not order.delivered_at:
            order.delivered_at = datetime.utcnow()

    if tracking_number:
        order.tracking_number = sanitize_string(tracking_number, max_length=50)

    if notes:
        order.delivery_notes = sanitize_string(notes, max_length=500)

    db.session.commit()

    current_app.logger.info(f"Order {order_number} status changed: {old_status} -> {new_status} by {current_user.email}")

    return jsonify({
        'success': True,
        'order_number': order.order_number,
        'status': order.status
    })


@admin_bp.route('/orders/<order_number>/print', methods=['POST'])
@login_required
@admin_required
def print_order(order_number):
    """Send order to printer"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    item = order.items.first()
    if not item or not item.pdf_file:
        return jsonify({'error': 'No PDF available'}), 400

    import os
    if not os.path.exists(item.pdf_file):
        return jsonify({'error': 'PDF file not found'}), 404

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

        current_app.logger.info(f"Print job started for order {order_number} by {current_user.email}")

    return jsonify(result)


@admin_bp.route('/print-queue', methods=['GET'])
@login_required
@admin_required
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
@login_required
@admin_required
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
@login_required
@admin_required
def mark_message_read(message_id):
    """Mark message as read"""
    message = ContactMessage.query.get(message_id)
    if not message:
        return jsonify({'error': 'Message not found'}), 404

    message.is_read = True
    db.session.commit()

    return jsonify({'success': True})
