"""
Payment API Routes - M-Pesa Integration
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime

from src.models import db, Order, Payment, PrintJob
from src.services.mpesa import MpesaService
from src.services.card_processor import PrintService


def auto_print_order(order):
    """Automatically send order to printer after payment"""
    try:
        item = order.items.first()
        if not item or not item.pdf_file:
            current_app.logger.error(f"[AUTO-PRINT] No PDF for order {order.order_number}")
            return False

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
                status='printing' if not result.get('mock') else 'completed',
                started_at=datetime.utcnow()
            )
            if result.get('mock'):
                print_job.completed_at = datetime.utcnow()
                order.status = 'printed'
                order.printed_at = datetime.utcnow()
                item.status = 'printed'
                item.printed_count = item.quantity

            db.session.add(print_job)
            db.session.commit()

            current_app.logger.info(f"[AUTO-PRINT] Order {order.order_number} sent to printer: {result.get('job_id')}")
            return True
        else:
            current_app.logger.error(f"[AUTO-PRINT] Failed for order {order.order_number}: {result.get('message')}")
            return False

    except Exception as e:
        current_app.logger.error(f"[AUTO-PRINT] Error for order {order.order_number}: {e}")
        return False

payments_bp = Blueprint('payments', __name__, url_prefix='/api/payments')


def get_mpesa_service():
    """Get configured M-Pesa service instance"""
    return MpesaService(
        consumer_key=current_app.config.get('MPESA_CONSUMER_KEY'),
        consumer_secret=current_app.config.get('MPESA_CONSUMER_SECRET'),
        shortcode=current_app.config.get('MPESA_SHORTCODE'),
        passkey=current_app.config.get('MPESA_PASSKEY'),
        callback_url=current_app.config.get('MPESA_CALLBACK_URL'),
        env=current_app.config.get('MPESA_ENV', 'sandbox')
    )


@payments_bp.route('/mpesa/initiate', methods=['POST'])
def initiate_mpesa():
    """
    Initiate M-Pesa STK Push payment

    Expects JSON:
    {
        "order_number": "PK-240101-ABCD",
        "phone": "0712345678"
    }
    """
    data = request.get_json()
    order_number = data.get('order_number')
    phone = data.get('phone')

    if not order_number or not phone:
        return jsonify({'error': 'Order number and phone are required'}), 400

    # Find order
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if order.payment_status == 'paid':
        return jsonify({'error': 'Order is already paid'}), 400

    # Check if M-Pesa is configured
    if not current_app.config.get('MPESA_CONSUMER_KEY'):
        # Mock payment for development
        if current_app.config.get('MOCK_PRINTING', True):
            # Create mock payment
            payment = Payment(
                order_id=order.id,
                transaction_id=f"MOCK-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                payment_method='mpesa',
                amount=order.total,
                status='completed',
                mpesa_receipt=f"QK{datetime.now().strftime('%H%M%S')}ABC",
                phone_number=phone,
                completed_at=datetime.utcnow()
            )
            db.session.add(payment)

            order.payment_status = 'paid'
            order.payment_method = 'mpesa'
            order.payment_reference = payment.mpesa_receipt
            order.paid_at = datetime.utcnow()
            order.status = 'processing'
            db.session.commit()

            # AUTO-PRINT: Trigger printing immediately after payment
            print_success = auto_print_order(order)

            return jsonify({
                'success': True,
                'mock': True,
                'message': 'Payment successful - printing started!' if print_success else 'Payment successful (MOCK MODE)',
                'receipt': payment.mpesa_receipt,
                'auto_printed': print_success
            })
        else:
            return jsonify({'error': 'M-Pesa not configured'}), 500

    # Initiate real M-Pesa payment
    mpesa = get_mpesa_service()
    result = mpesa.initiate_stk_push(
        phone_number=phone,
        amount=order.total,
        account_reference=order_number,
        description="PrintKe Card"
    )

    if result['success']:
        # Create pending payment record
        payment = Payment(
            order_id=order.id,
            payment_method='mpesa',
            amount=order.total,
            phone_number=MpesaService._format_phone(phone),
            checkout_request_id=result['checkout_request_id'],
            merchant_request_id=result['merchant_request_id'],
            status='pending'
        )
        db.session.add(payment)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Please check your phone and enter M-Pesa PIN',
            'checkout_request_id': result['checkout_request_id']
        })
    else:
        return jsonify({
            'success': False,
            'error': result.get('error', 'Payment initiation failed')
        }), 400


@payments_bp.route('/mpesa/callback', methods=['POST'])
def mpesa_callback():
    """
    M-Pesa callback endpoint - receives payment confirmation from Safaricom
    """
    callback_data = request.get_json()
    current_app.logger.info(f"[MPESA CALLBACK] {callback_data}")

    mpesa = get_mpesa_service()
    result = mpesa.process_callback(callback_data)

    if result['success'] and result.get('paid'):
        checkout_request_id = result.get('checkout_request_id')

        # Find payment by checkout_request_id
        payment = Payment.query.filter_by(checkout_request_id=checkout_request_id).first()

        if payment:
            payment.status = 'completed'
            payment.mpesa_receipt = result.get('receipt')
            payment.transaction_id = result.get('receipt')
            payment.completed_at = datetime.utcnow()

            # Update order
            order = payment.order
            order.payment_status = 'paid'
            order.payment_method = 'mpesa'
            order.payment_reference = result.get('receipt')
            order.paid_at = datetime.utcnow()
            order.status = 'processing'

            db.session.commit()
            current_app.logger.info(f"[MPESA] Payment confirmed for order {order.order_number}")

    elif result['success'] and not result.get('paid'):
        # Payment failed or cancelled
        checkout_request_id = result.get('checkout_request_id')
        payment = Payment.query.filter_by(checkout_request_id=checkout_request_id).first()

        if payment:
            payment.status = 'failed'
            payment.error_message = result.get('error', 'Payment failed')
            db.session.commit()

    # Always return success to Safaricom
    return jsonify({'ResultCode': 0, 'ResultDesc': 'Accepted'})


@payments_bp.route('/mpesa/status/<checkout_request_id>', methods=['GET'])
def check_payment_status(checkout_request_id):
    """Check status of M-Pesa payment"""
    payment = Payment.query.filter_by(checkout_request_id=checkout_request_id).first()

    if not payment:
        return jsonify({'error': 'Payment not found'}), 404

    if payment.status == 'completed':
        return jsonify({
            'status': 'completed',
            'paid': True,
            'receipt': payment.mpesa_receipt,
            'order_status': payment.order.status
        })
    elif payment.status == 'failed':
        return jsonify({
            'status': 'failed',
            'paid': False,
            'error': payment.error_message
        })
    else:
        # Query M-Pesa for status
        if current_app.config.get('MPESA_CONSUMER_KEY'):
            mpesa = get_mpesa_service()
            result = mpesa.query_stk_status(checkout_request_id)

            if result['success'] and result.get('paid'):
                # Update payment
                payment.status = 'completed'
                payment.completed_at = datetime.utcnow()
                db.session.commit()

                return jsonify({
                    'status': 'completed',
                    'paid': True
                })

        return jsonify({
            'status': 'pending',
            'paid': False,
            'message': 'Waiting for payment confirmation'
        })


@payments_bp.route('/order/<order_number>/status', methods=['GET'])
def check_order_payment(order_number):
    """Check payment status for an order"""
    order = Order.query.filter_by(order_number=order_number).first()

    if not order:
        return jsonify({'error': 'Order not found'}), 404

    return jsonify({
        'order_number': order.order_number,
        'payment_status': order.payment_status,
        'order_status': order.status,
        'total': order.total,
        'paid_at': order.paid_at.isoformat() if order.paid_at else None,
        'receipt': order.payment_reference
    })
