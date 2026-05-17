"""
utils/validators.py - WTForms custom validators.
"""
import re
from wtforms.validators import ValidationError


def phone_validator(form, field):
    """Validate Indian phone number (10 digits, optionally starting with +91)."""
    value = re.sub(r'\D', '', field.data or '')
    if len(value) not in (10, 12):
        raise ValidationError('Enter a valid 10-digit phone number.')


def pin_validator(form, field):
    """Validate Indian 6-digit PIN code."""
    if field.data and not re.match(r'^\d{6}$', field.data):
        raise ValidationError('PIN code must be 6 digits.')


def positive_amount(form, field):
    """Ensure amount is positive."""
    if field.data is not None and field.data < 0:
        raise ValidationError('Amount must be a positive number.')
