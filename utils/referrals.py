"""
utils/referrals.py - Signed customer referral link helpers.
"""
from itsdangerous import BadSignature, URLSafeSerializer
from flask import current_app


REFERRAL_LINK_SALT = 'homzho-customer-referral'


def _serializer() -> URLSafeSerializer:
    secret_key = current_app.config.get('SECRET_KEY')
    if not secret_key:
        raise RuntimeError('SECRET_KEY is required to generate referral links.')
    return URLSafeSerializer(secret_key, salt=REFERRAL_LINK_SALT)


def generate_referral_token(customer_id: int) -> str:
    """Return a signed token that identifies the referring customer."""
    return _serializer().dumps({'cust_id': int(customer_id)})


def load_referral_customer_id(token: str):
    """Return customer id from a signed token, or None when invalid."""
    try:
        payload = _serializer().loads(token)
        customer_id = int(payload.get('cust_id'))
    except (BadSignature, TypeError, ValueError, AttributeError):
        return None
    return customer_id if customer_id > 0 else None
