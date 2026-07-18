"""
services/maintenance_service.py - Maintenance reminder logic and inventory deduction.
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


def deduct_inventory_for_maintenance(service_record, parts_list: list, created_by: str) -> list:
    """Deduct consumed inventory items for a maintenance service record.

    Args:
        service_record: The saved Maintenance ORM instance (service_id must be set).
        parts_list: List of dicts — [{'item_id': int, 'quantity': float}, ...]
        created_by: Username of the technician / logged-in user.

    Returns:
        A list of warning strings — empty if everything deducted cleanly.
        Each warning means a quantity was capped due to insufficient stock.

    Side effects (within the caller's open transaction):
        - Decrements InventoryItem.current_stock for each part.
        - Creates one InventoryMovement(type='Out') per part, linked to
          reference_type='maintenance', reference_id=service_record.service_id.
    """
    from models.inventory import InventoryItem, InventoryMovement  # local import avoids circular

    warnings = []

    for part in parts_list:
        item_id = part.get('item_id')
        requested_qty = part.get('quantity', 0)

        # Skip rows with no item or zero quantity
        if not item_id or requested_qty <= 0:
            continue

        item = db.session.get(InventoryItem, item_id)
        if not item or not item.is_active:
            warnings.append(f'Inventory item ID {item_id} not found — skipped.')
            continue

        # Cap deduction to what's available (never go below 0)
        available = float(item.current_stock or 0)
        deduct_qty = min(float(requested_qty), available)

        if deduct_qty <= 0:
            warnings.append(
                f'"{item.item_name}" has no stock available (0 {item.unit}) — skipped.'
            )
            continue

        if deduct_qty < float(requested_qty):
            warnings.append(
                f'"{item.item_name}": only {available:g} {item.unit} available; '
                f'deducted {deduct_qty:g} instead of {requested_qty:g}.'
            )

        # Deduct stock
        item.current_stock = round(available - deduct_qty, 4)

        # Record movement (Out) linked to this maintenance service record
        movement = InventoryMovement(
            item_id=item.item_id,
            movement_date=service_record.service_date,
            movement_type='Out',
            quantity=deduct_qty,
            unit_cost=float(item.unit_cost or 0),
            reference_type='maintenance',
            reference_id=service_record.service_id,
            notes=(
                f'Used during {service_record.service_type} — '
                f'Service #{service_record.service_id} '
                f'(Machine #{service_record.machine_id})'
            ),
            created_by=created_by,
        )
        db.session.add(movement)

    return warnings

