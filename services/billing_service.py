"""
services/billing_service.py - Billing reminder logic.
"""
from datetime import date, timedelta
from models.customer import Customer
from models.reminder_log import ReminderLog
from extensions import db


def get_billing_reminders(days: int = 7) -> list:
    """Return active customers whose next_billing_date is within `days` days or overdue."""
    today = date.today()
    cutoff = today + timedelta(days=days)
    return (
        Customer.query
        .filter(Customer.customer_status == 'Active')
        .filter(Customer.next_billing_date <= cutoff)
        .order_by(Customer.next_billing_date.asc())
        .all()
    )


def get_overdue_payments() -> list:
    """Customers whose next_billing_date is in the past."""
    today = date.today()
    return (
        Customer.query
        .filter(Customer.customer_status == 'Active')
        .filter(Customer.next_billing_date < today)
        .order_by(Customer.next_billing_date.asc())
        .all()
    )


def mark_reminder_sent(customer_id: int, reminder_type: str, sent_by: str) -> ReminderLog:
    """Create a reminder log entry marking a reminder as Sent."""
    log = ReminderLog(
        customer_id=customer_id,
        reminder_type=reminder_type,
        scheduled_date=date.today(),
        sent_date=db.func.now(),
        status='Sent',
        sent_by=sent_by,
    )
    db.session.add(log)
    db.session.commit()
    return log
