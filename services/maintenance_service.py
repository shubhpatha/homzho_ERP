"""
services/maintenance_service.py - Maintenance reminder logic.
"""
from datetime import date, timedelta
from models.machine import Machine
from models.reminder_log import ReminderLog
from extensions import db


def get_maintenance_due(days: int = 30) -> list:
    """Return machines whose next_service_date is within `days` days."""
    today = date.today()
    cutoff = today + timedelta(days=days)
    return (
        Machine.query
        .filter(Machine.machine_status == 'Installed')
        .filter(Machine.next_service_date <= cutoff)
        .filter(Machine.next_service_date >= today)
        .order_by(Machine.next_service_date.asc())
        .all()
    )


def get_overdue_maintenance() -> list:
    """Return installed machines with overdue maintenance."""
    today = date.today()
    return (
        Machine.query
        .filter(Machine.machine_status == 'Installed')
        .filter(Machine.next_service_date < today)
        .order_by(Machine.next_service_date.asc())
        .all()
    )


def mark_maintenance_reminder_sent(machine_id: int, sent_by: str) -> ReminderLog:
    """Create a reminder log entry for a maintenance reminder."""
    log = ReminderLog(
        machine_id=machine_id,
        reminder_type='Maintenance',
        scheduled_date=date.today(),
        sent_date=db.func.now(),
        status='Sent',
        sent_by=sent_by,
    )
    db.session.add(log)
    db.session.commit()
    return log
