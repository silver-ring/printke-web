"""
Payment API Routes - FastAPI with M-Pesa Integration
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models import Order, Payment, PrintJob
from src.schemas.payments import (
    PaymentInitiate, PaymentResponse, PaymentStatusResponse, MpesaCallback
)
from src.core.config import settings
from src.services.mpesa import MpesaService
from src.services.card_processor import PrintService

router = APIRouter()
logger = logging.getLogger(__name__)


async def auto_print_order(order: Order, db: AsyncSession) -> bool:
    """Automatically send order to printer after payment"""
    try:
        if not order.items:
            logger.error(f"[AUTO-PRINT] No items for order {order.order_number}")
            return False

        item = order.items[0]
        if not item.pdf_file:
            logger.error(f"[AUTO-PRINT] No PDF for order {order.order_number}")
            return False

        printer = PrintService(
            printer_name=settings.printer_name,
            mock_mode=settings.mock_printing
        )

        result = printer.print_card(item.pdf_file, copies=item.quantity)

        if result["success"]:
            order.status = "printing"
            item.status = "printing"

            # Create print job record
            print_job = PrintJob(
                order_item_id=item.id,
                job_id=result.get("job_id"),
                copies=item.quantity,
                status="printing" if not result.get("mock") else "completed",
                started_at=datetime.utcnow()
            )

            if result.get("mock"):
                print_job.completed_at = datetime.utcnow()
                order.status = "printed"
                order.printed_at = datetime.utcnow()
                item.status = "printed"
                item.printed_count = item.quantity

            db.add(print_job)
            await db.commit()

            logger.info(f"[AUTO-PRINT] Order {order.order_number} sent to printer: {result.get('job_id')}")
            return True
        else:
            logger.error(f"[AUTO-PRINT] Failed for order {order.order_number}: {result.get('message')}")
            return False

    except Exception as e:
        logger.error(f"[AUTO-PRINT] Error for order {order.order_number}: {e}")
        return False


def get_mpesa_service() -> MpesaService:
    """Get configured M-Pesa service instance"""
    return MpesaService(
        consumer_key=settings.mpesa_consumer_key,
        consumer_secret=settings.mpesa_consumer_secret,
        shortcode=settings.mpesa_shortcode,
        passkey=settings.mpesa_passkey,
        callback_url=settings.mpesa_callback_url,
        env=settings.mpesa_env
    )


@router.post("/mpesa/initiate", response_model=PaymentResponse)
async def initiate_mpesa(request: PaymentInitiate, db: AsyncSession = Depends(get_db)):
    """
    Initiate M-Pesa STK Push payment

    - **order_number**: Order number (PK-YYMMDD-XXXX format)
    - **phone**: Kenyan phone number (0712345678 format)
    """
    # Find order
    result = await db.execute(
        select(Order)
        .where(Order.order_number == request.order_number)
        .options(selectinload(Order.items))
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.payment_status == "paid":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order is already paid")

    # Format phone for M-Pesa
    import re
    phone = re.sub(r'[\s\-\(\)\.]', '', request.phone)
    if phone.startswith('+'):
        phone = phone[1:]
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    elif phone.startswith('7') or phone.startswith('1'):
        phone = '254' + phone

    # Check if M-Pesa is configured
    if not settings.mpesa_consumer_key:
        # Mock payment for development
        if settings.mock_printing:
            # Create mock payment
            payment = Payment(
                order_id=order.id,
                transaction_id=f"MOCK-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                payment_method="mpesa",
                amount=order.total,
                status="completed",
                mpesa_receipt=f"QK{datetime.now().strftime('%H%M%S')}ABC",
                phone_number=phone,
                completed_at=datetime.utcnow()
            )
            db.add(payment)

            order.payment_status = "paid"
            order.payment_method = "mpesa"
            order.payment_reference = payment.mpesa_receipt
            order.paid_at = datetime.utcnow()
            order.status = "processing"
            await db.commit()

            # Refresh to get relationships
            await db.refresh(order)

            # AUTO-PRINT: Trigger printing immediately after payment
            print_success = await auto_print_order(order, db)

            return PaymentResponse(
                success=True,
                mock=True,
                message="Payment successful - printing started!" if print_success else "Payment successful (MOCK MODE)",
                receipt=payment.mpesa_receipt,
                auto_printed=print_success
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="M-Pesa not configured"
            )

    # Initiate real M-Pesa payment
    mpesa = get_mpesa_service()
    mpesa_result = mpesa.initiate_stk_push(
        phone_number=phone,
        amount=order.total,
        account_reference=request.order_number,
        description="PrintKe Card"
    )

    if mpesa_result["success"]:
        # Create pending payment record
        payment = Payment(
            order_id=order.id,
            payment_method="mpesa",
            amount=order.total,
            phone_number=phone,
            checkout_request_id=mpesa_result["checkout_request_id"],
            merchant_request_id=mpesa_result["merchant_request_id"],
            status="pending"
        )
        db.add(payment)
        await db.commit()

        return PaymentResponse(
            success=True,
            message="Please check your phone and enter M-Pesa PIN",
            checkout_request_id=mpesa_result["checkout_request_id"]
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mpesa_result.get("error", "Payment initiation failed")
        )


@router.post("/mpesa/callback")
async def mpesa_callback(callback: MpesaCallback, db: AsyncSession = Depends(get_db)):
    """
    M-Pesa callback endpoint - receives payment confirmation from Safaricom
    """
    logger.info(f"[MPESA CALLBACK] {callback}")

    stk_callback = callback.Body.stkCallback
    checkout_request_id = stk_callback.CheckoutRequestID
    result_code = stk_callback.ResultCode

    if result_code == 0:
        # Payment successful - extract details
        payment_info = {}
        if stk_callback.CallbackMetadata:
            for item in stk_callback.CallbackMetadata.Item:
                if item.Name == "Amount":
                    payment_info["amount"] = item.Value
                elif item.Name == "MpesaReceiptNumber":
                    payment_info["receipt"] = item.Value
                elif item.Name == "PhoneNumber":
                    payment_info["phone"] = item.Value

        # Find and update payment
        result = await db.execute(
            select(Payment)
            .where(Payment.checkout_request_id == checkout_request_id)
            .options(selectinload(Payment.order).selectinload(Order.items))
        )
        payment = result.scalar_one_or_none()

        if payment:
            payment.status = "completed"
            payment.mpesa_receipt = payment_info.get("receipt")
            payment.transaction_id = payment_info.get("receipt")
            payment.completed_at = datetime.utcnow()

            # Update order
            order = payment.order
            order.payment_status = "paid"
            order.payment_method = "mpesa"
            order.payment_reference = payment_info.get("receipt")
            order.paid_at = datetime.utcnow()
            order.status = "processing"

            await db.commit()
            logger.info(f"[MPESA] Payment confirmed for order {order.order_number}")

            # AUTO-PRINT after successful payment
            await auto_print_order(order, db)

    else:
        # Payment failed or cancelled
        result = await db.execute(
            select(Payment).where(Payment.checkout_request_id == checkout_request_id)
        )
        payment = result.scalar_one_or_none()

        if payment:
            payment.status = "failed"
            payment.error_message = stk_callback.ResultDesc
            await db.commit()

    # Always return success to Safaricom
    return {"ResultCode": 0, "ResultDesc": "Accepted"}


@router.get("/mpesa/status/{checkout_request_id}")
async def check_payment_status(checkout_request_id: str, db: AsyncSession = Depends(get_db)):
    """Check status of M-Pesa payment"""
    result = await db.execute(
        select(Payment)
        .where(Payment.checkout_request_id == checkout_request_id)
        .options(selectinload(Payment.order))
    )
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    if payment.status == "completed":
        return {
            "status": "completed",
            "paid": True,
            "receipt": payment.mpesa_receipt,
            "order_status": payment.order.status
        }
    elif payment.status == "failed":
        return {
            "status": "failed",
            "paid": False,
            "error": payment.error_message
        }
    else:
        # Query M-Pesa for status if configured
        if settings.mpesa_consumer_key:
            mpesa = get_mpesa_service()
            mpesa_result = mpesa.query_stk_status(checkout_request_id)

            if mpesa_result["success"] and mpesa_result.get("paid"):
                payment.status = "completed"
                payment.completed_at = datetime.utcnow()
                await db.commit()

                return {"status": "completed", "paid": True}

        return {
            "status": "pending",
            "paid": False,
            "message": "Waiting for payment confirmation"
        }


@router.get("/order/{order_number}/status", response_model=PaymentStatusResponse)
async def check_order_payment(order_number: str, db: AsyncSession = Depends(get_db)):
    """Check payment status for an order"""
    result = await db.execute(select(Order).where(Order.order_number == order_number))
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return PaymentStatusResponse(
        order_number=order.order_number,
        payment_status=order.payment_status,
        order_status=order.status,
        total=order.total,
        paid_at=order.paid_at,
        receipt=order.payment_reference
    )
