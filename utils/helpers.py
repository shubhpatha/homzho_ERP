"""
utils/helpers.py - General-purpose helper functions.
"""
import os
import re
from datetime import date, datetime
from flask import current_app
from extensions import db
from models.activity_log import ActivityLog
from models.payment import Payment


# ---------------------------------------------------------------------------
# Invoice number generation
# ---------------------------------------------------------------------------

def generate_invoice_no(payment_date: date) -> str:
    """
    Generate a unique invoice number in format: INV-YYYYMMDD-NNN
    Sequential number resets daily and does NOT reuse numbers from deleted payments.
    """
    date_str = payment_date.strftime('%Y%m%d')
    prefix = f'INV-{date_str}-'

    # Count all invoices for that date (including soft-deleted if applicable)
    # We use the max sequence number from existing records to avoid reuse
    existing = (
        Payment.query
        .filter(Payment.invoice_no.like(f'{prefix}%'))
        .with_entities(Payment.invoice_no)
        .all()
    )

    max_seq = 0
    for (inv,) in existing:
        try:
            seq = int(inv.split('-')[-1])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, IndexError):
            pass

    return f'{prefix}{max_seq + 1:03d}'


# ---------------------------------------------------------------------------
# Activity logging
# ---------------------------------------------------------------------------

def log_activity(user_name: str, action_type: str, module_name: str,
                 record_id=None, remarks: str = None, ip_address: str = None):
    """
    Write an audit entry to activity_logs table.
    Call this from every route that modifies data.
    """
    try:
        log = ActivityLog(
            user_name=user_name,
            action_type=action_type,
            module_name=module_name,
            record_id=record_id,
            remarks=remarks,
            ip_address=ip_address,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as exc:
        # Log to file but don't break the main request
        current_app.logger.error(f'Failed to write activity log: {exc}')
        db.session.rollback()


# ---------------------------------------------------------------------------
# Phone number sanitizer
# ---------------------------------------------------------------------------

def clean_phone(phone: str) -> str:
    """Strip non-digit characters and return normalised phone number."""
    return re.sub(r'\D', '', phone or '')


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def today() -> date:
    return date.today()


def days_until(target_date: date) -> int:
    """Return number of days between today and a future date (negative if past)."""
    if target_date is None:
        return 9999
    return (target_date - today()).days


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------

def get_page_items(query, page: int, per_page: int = None):
    """Return a SQLAlchemy Pagination object."""
    per_page = per_page or current_app.config.get('ITEMS_PER_PAGE', 20)
    return query.paginate(page=page, per_page=per_page, error_out=False)


# ---------------------------------------------------------------------------
# Folder creation
# ---------------------------------------------------------------------------

def ensure_dir(path: str):
    """Create directory tree if it doesn't exist."""
    os.makedirs(path, exist_ok=True)
