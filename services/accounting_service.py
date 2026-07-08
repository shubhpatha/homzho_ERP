"""
services/accounting_service.py - Synchronize source records into account ledger.
"""
from sqlalchemy import func
from extensions import db
from models.accounting import AccountLedger
from models.expense import Expense
from models.maintenance import Maintenance
from models.payment import Payment


def _amount(value):
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def upsert_ledger_entry(
    *,
    entry_date,
    entry_type,
    category,
    amount,
    source_type,
    source_id,
    payment_mode=None,
    party_name=None,
    description=None,
    reference_no=None,
    created_by=None,
):
    """Create, update, or remove a ledger entry for one source amount."""
    normalized_amount = _amount(amount)
    entry = AccountLedger.query.filter_by(
        source_type=source_type,
        source_id=source_id,
        entry_type=entry_type,
        category=category,
    ).first()

    if normalized_amount <= 0:
        if entry:
            db.session.delete(entry)
        return None

    if not entry:
        entry = AccountLedger(
            source_type=source_type,
            source_id=source_id,
            entry_type=entry_type,
            category=category,
        )
        db.session.add(entry)

    entry.entry_date = entry_date
    entry.amount = normalized_amount
    entry.payment_mode = payment_mode
    entry.party_name = party_name
    entry.description = description
    entry.reference_no = reference_no
    entry.created_by = created_by
    return entry


def sync_payment_to_ledger(payment, created_by=None):
    """Track customer collections as income."""
    customer = payment.customer
    return upsert_ledger_entry(
        entry_date=payment.payment_date,
        entry_type='Income',
        category='Customer Collection',
        amount=payment.amount_paid,
        payment_mode=payment.payment_mode,
        party_name=customer.cust_name if customer else None,
        description=payment.remark or 'Customer payment',
        source_type='payment',
        source_id=payment.payment_id,
        reference_no=payment.invoice_no,
        created_by=created_by or payment.collected_by,
    )


def sync_expense_to_ledger(expense, created_by=None):
    """Track manually entered business expenses."""
    return upsert_ledger_entry(
        entry_date=expense.expense_date,
        entry_type='Expense',
        category=expense.expense_category,
        amount=expense.amount,
        payment_mode=expense.payment_mode,
        party_name=expense.paid_to,
        description=expense.remarks,
        source_type='expense',
        source_id=expense.expense_id,
        reference_no=str(expense.expense_id),
        created_by=created_by or expense.approved_by,
    )


def sync_maintenance_to_ledger(record, created_by=None):
    """Track both maintenance and travel costs from service records."""
    machine_serial = record.machine.machine_serial_no if record.machine else f'Machine #{record.machine_id}'
    common = {
        'entry_date': record.service_date,
        'entry_type': 'Expense',
        'payment_mode': 'Cash',
        'party_name': record.technician_name,
        'source_type': 'maintenance',
        'source_id': record.service_id,
        'reference_no': str(record.service_id),
        'created_by': created_by,
    }
    main = upsert_ledger_entry(
        category='Maintenance',
        amount=record.main_exp,
        description=f'{record.service_type} for {machine_serial}',
        **common,
    )
    travel = upsert_ledger_entry(
        category='Maintenance Travel',
        amount=record.travel_exp,
        description=f'Travel for {record.service_type} - {machine_serial}',
        **common,
    )
    return main, travel


def ledger_total(entry_type, start_date=None, end_date=None):
    query = db.session.query(func.coalesce(func.sum(AccountLedger.amount), 0)).filter(
        AccountLedger.entry_type == entry_type
    )
    if start_date:
        query = query.filter(AccountLedger.entry_date >= start_date)
    if end_date:
        query = query.filter(AccountLedger.entry_date <= end_date)
    return float(query.scalar() or 0)


def ledger_breakdown(entry_type, start_date=None, end_date=None):
    query = db.session.query(
        AccountLedger.category.label('category'),
        func.sum(AccountLedger.amount).label('total'),
    ).filter(AccountLedger.entry_type == entry_type)
    if start_date:
        query = query.filter(AccountLedger.entry_date >= start_date)
    if end_date:
        query = query.filter(AccountLedger.entry_date <= end_date)
    return query.group_by(AccountLedger.category).order_by(AccountLedger.category).all()


def backfill_account_ledger():
    """Populate ledger rows from existing payments, expenses, and maintenance."""
    for payment in Payment.query.all():
        sync_payment_to_ledger(payment)
    for expense in Expense.query.all():
        sync_expense_to_ledger(expense)
    for record in Maintenance.query.all():
        sync_maintenance_to_ledger(record)
