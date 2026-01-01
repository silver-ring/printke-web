"""
M-Pesa Integration Service
Safaricom Daraja API integration for STK Push payments
"""
import base64
import httpx
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class MpesaService:
    """
    M-Pesa STK Push integration for Kenya payments

    To get credentials:
    1. Register at https://developer.safaricom.co.ke
    2. Create an app and get Consumer Key/Secret
    3. For sandbox, use test shortcode 174379
    4. For production, apply for a paybill/till number
    """

    SANDBOX_URL = "https://sandbox.safaricom.co.ke"
    PRODUCTION_URL = "https://api.safaricom.co.ke"

    def __init__(self, consumer_key, consumer_secret, shortcode, passkey, callback_url, env='sandbox'):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.shortcode = shortcode
        self.passkey = passkey
        self.callback_url = callback_url
        self.base_url = self.SANDBOX_URL if env == 'sandbox' else self.PRODUCTION_URL
        self.access_token = None
        self.token_expiry = None

    def _get_access_token(self):
        """Get OAuth access token from Safaricom"""
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token

        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        credentials = base64.b64encode(
            f"{self.consumer_key}:{self.consumer_secret}".encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {credentials}"
        }

        try:
            with httpx.Client() as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                self.access_token = data['access_token']
                # Token expires in 3600 seconds, we refresh at 3000
                self.token_expiry = datetime.now() + timedelta(seconds=3000)
                return self.access_token
        except Exception as e:
            logger.error(f"[MPESA] Failed to get access token: {e}")
            raise

    def _generate_password(self, timestamp):
        """Generate the password for STK push"""
        data = f"{self.shortcode}{self.passkey}{timestamp}"
        return base64.b64encode(data.encode()).decode()

    def initiate_stk_push(self, phone_number, amount, account_reference, description="Payment"):
        """
        Initiate STK Push to customer's phone

        Args:
            phone_number: Customer phone (254XXXXXXXXX format)
            amount: Amount in KES
            account_reference: Order number or reference
            description: Transaction description

        Returns:
            dict with response from M-Pesa
        """
        # Format phone number
        phone = self._format_phone(phone_number)

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self._generate_password(timestamp)

        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"

        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": self.shortcode,
            "PhoneNumber": phone,
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference[:12],  # Max 12 chars
            "TransactionDesc": description[:13]  # Max 13 chars
        }

        try:
            logger.info(f"[MPESA] Initiating STK Push: {phone}, KES {amount}")
            with httpx.Client() as client:
                response = client.post(url, json=payload, headers=headers)
                data = response.json()

                if response.status_code == 200 and data.get('ResponseCode') == '0':
                    logger.info(f"[MPESA] STK Push initiated: {data.get('CheckoutRequestID')}")
                    return {
                        'success': True,
                        'checkout_request_id': data.get('CheckoutRequestID'),
                        'merchant_request_id': data.get('MerchantRequestID'),
                        'response_description': data.get('ResponseDescription')
                    }
                else:
                    logger.error(f"[MPESA] STK Push failed: {data}")
                    return {
                        'success': False,
                        'error': data.get('errorMessage', data.get('ResponseDescription', 'Unknown error'))
                    }

        except Exception as e:
            logger.error(f"[MPESA] Error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def query_stk_status(self, checkout_request_id):
        """
        Query the status of an STK Push transaction

        Args:
            checkout_request_id: The CheckoutRequestID from initiate_stk_push

        Returns:
            dict with transaction status
        """
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self._generate_password(timestamp)

        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"

        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id
        }

        try:
            with httpx.Client() as client:
                response = client.post(url, json=payload, headers=headers)
                data = response.json()

                result_code = data.get('ResultCode')

                if result_code == '0':
                    return {
                        'success': True,
                        'paid': True,
                        'message': 'Payment successful'
                    }
                elif result_code == '1032':
                    return {
                        'success': True,
                        'paid': False,
                        'message': 'Transaction cancelled by user'
                    }
                elif result_code == '1037':
                    return {
                        'success': True,
                        'paid': False,
                        'message': 'Transaction timed out'
                    }
                else:
                    return {
                        'success': True,
                        'paid': False,
                        'message': data.get('ResultDesc', 'Transaction failed')
                    }

        except Exception as e:
            logger.error(f"[MPESA] Query error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def process_callback(self, callback_data):
        """
        Process M-Pesa callback after payment

        Args:
            callback_data: JSON data from M-Pesa callback

        Returns:
            dict with parsed payment info
        """
        try:
            body = callback_data.get('Body', {}).get('stkCallback', {})
            result_code = body.get('ResultCode')
            result_desc = body.get('ResultDesc')
            checkout_request_id = body.get('CheckoutRequestID')
            merchant_request_id = body.get('MerchantRequestID')

            if result_code == 0:
                # Payment successful - extract details
                metadata = body.get('CallbackMetadata', {}).get('Item', [])
                payment_info = {}

                for item in metadata:
                    name = item.get('Name')
                    value = item.get('Value')
                    if name == 'Amount':
                        payment_info['amount'] = value
                    elif name == 'MpesaReceiptNumber':
                        payment_info['receipt'] = value
                    elif name == 'TransactionDate':
                        payment_info['date'] = value
                    elif name == 'PhoneNumber':
                        payment_info['phone'] = value

                logger.info(f"[MPESA] Payment successful: {payment_info.get('receipt')}")

                return {
                    'success': True,
                    'paid': True,
                    'checkout_request_id': checkout_request_id,
                    'merchant_request_id': merchant_request_id,
                    **payment_info
                }
            else:
                logger.info(f"[MPESA] Payment failed: {result_desc}")
                return {
                    'success': True,
                    'paid': False,
                    'checkout_request_id': checkout_request_id,
                    'error': result_desc
                }

        except Exception as e:
            logger.error(f"[MPESA] Callback processing error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    def _format_phone(phone):
        """Convert phone to 254XXXXXXXXX format"""
        phone = str(phone).strip().replace(' ', '').replace('-', '')

        if phone.startswith('+'):
            phone = phone[1:]
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        if not phone.startswith('254'):
            phone = '254' + phone

        return phone
