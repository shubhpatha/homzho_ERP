"""
services/export_service.py - CSV export using Pandas.
"""
import os
import io
from datetime import datetime
import pandas as pd
from flask import current_app
from extensions import db
from models.customer import Customer
from models.payment import Payment
from models.maintenance import Maintenance
from models.expense import Expense


def _ensure_export_dir():
    export_dir = current_app.config['EXPORT_FOLDER']
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


# ---------------------------------------------------------------------------
# Export to CSV bytes (for HTTP response streaming)
# ---------------------------------------------------------------------------

def export_customers_csv() -> bytes:
    """Return customers CSV as bytes."""
    customers = Customer.query.all()
    rows = []
    for c in customers:
        rows.append({
            'ID': c.cust_id,
            'Name': c.cust_name,
            'Contact': c.contact_number,
            'Email': c.email_id,
            'Plan': c.plan_name,
            'Plan Duration (Months)': c.plan_duration_months,
            'Plan Start': c.plan_start_date,
            'Plan End': c.plan_end_date,
            'Monthly Rent': c.monthly_rent,
            'Status': c.customer_status,
            'City': c.city,
            'Next Billing Date': c.next_billing_date,
            'Machine Serial': c.machine_serial_no,
            'Installed By': c.installed_by,
            'Installation Date': c.installation_date,
        })
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode('utf-8-sig')


def export_payments_csv() -> bytes:
    """Return payments CSV as bytes."""
    payments = Payment.query.order_by(Payment.payment_date.desc()).all()
    rows = []
    for p in payments:
        rows.append({
            'Invoice No': p.invoice_no,
            'Customer ID': p.customer_id,
            'Customer Name': p.customer.cust_name if p.customer else '',
            'Payment Date': p.payment_date,
            'Amount Paid': p.amount_paid,
            'Amount Due': p.amount_due,
            'Mode': p.payment_mode,
            'Transaction ID': p.transaction_id,
            'Status': p.payment_status,
            'Days Overdue': p.days_overdue,
            'Collected By': p.collected_by,
            'Next Due Date': p.next_due_date,
        })
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode('utf-8-sig')


def export_maintenance_csv() -> bytes:
    """Return maintenance CSV as bytes."""
    records = Maintenance.query.order_by(Maintenance.service_date.desc()).all()
    rows = []
    for m in records:
        rows.append({
            'Service ID': m.service_id,
            'Machine ID': m.machine_id,
            'Machine Serial': m.machine.machine_serial_no if m.machine else '',
            'Customer ID': m.customer_id,
            'Service Date': m.service_date,
            'Next Service Date': m.next_service_date,
            'Service Type': m.service_type,
            'Technician': m.technician_name,
            'Filter Changed': m.filter_changed,
            'Water TDS': m.water_tds,
            'Main Expense': m.main_exp,
            'Travel Expense': m.travel_exp,
            'Feedback': m.customer_feedback,
        })
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode('utf-8-sig')


def export_expenses_csv() -> bytes:
    """Return expenses CSV as bytes."""
    expenses = Expense.query.order_by(Expense.expense_date.desc()).all()
    rows = []
    for e in expenses:
        rows.append({
            'ID': e.expense_id,
            'Date': e.expense_date,
            'Category': e.expense_category,
            'Amount': e.amount,
            'Mode': e.payment_mode,
            'Paid To': e.paid_to,
            'Remarks': e.remarks,
            'Approved By': e.approved_by,
        })
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode('utf-8-sig')


# ---------------------------------------------------------------------------
# CSV import template generators
# ---------------------------------------------------------------------------

def get_customer_import_template() -> bytes:
    """Return a blank CSV template for customer import."""
    columns = [
        'cust_name', 'contact_number', 'email_id', 'plan_name',
        'plan_duration_months', 'plan_start_date', 'monthly_rent',
        'payment_freq', 'deposit', 'address', 'city', 'pin', 'notes',
    ]
    df = pd.DataFrame(columns=columns)
    return df.to_csv(index=False).encode('utf-8-sig')


def get_machine_import_template() -> bytes:
    """Return a blank CSV template for machine import."""
    columns = [
        'machine_serial_no', 'model_name', 'machine_status',
        'machine_condition', 'tds_level', 'remarks',
    ]
    df = pd.DataFrame(columns=columns)
    return df.to_csv(index=False).encode('utf-8-sig')


# ---------------------------------------------------------------------------
# CSV import with full validation
# ---------------------------------------------------------------------------

def import_customers_csv(file_stream) -> dict:
    """
    Parse, validate, and bulk-insert customers from CSV.
    Returns {'success': True, 'count': N} or {'success': False, 'errors': [...]}
    """
    from models.customer import Customer
    from dateutil.relativedelta import relativedelta
    import datetime as dt

    try:
        df = pd.read_csv(file_stream, dtype=str).fillna('')
    except Exception as e:
        return {'success': False, 'errors': [f'Could not parse CSV: {e}']}

    required = ['cust_name', 'contact_number', 'plan_name', 'plan_start_date', 'monthly_rent']
    errors = []

    for col in required:
        if col not in df.columns:
            errors.append(f'Missing required column: {col}')

    if errors:
        return {'success': False, 'errors': errors}

    records = []
    for i, row in df.iterrows():
        line = i + 2  # 1-indexed, skipping header
        row_errors = []

        name = row.get('cust_name', '').strip()
        if not name:
            row_errors.append(f'Row {line}: cust_name is required.')

        phone = row.get('contact_number', '').strip()
        if not phone:
            row_errors.append(f'Row {line}: contact_number is required.')
        elif Customer.query.filter_by(contact_number=phone).first():
            row_errors.append(f'Row {line}: contact_number {phone} already exists.')

        plan_name = row.get('plan_name', '').strip()
        if not plan_name:
            row_errors.append(f'Row {line}: plan_name is required.')

        try:
            start = dt.date.fromisoformat(row.get('plan_start_date', '').strip())
        except ValueError:
            row_errors.append(f'Row {line}: plan_start_date must be YYYY-MM-DD format.')
            start = None

        try:
            rent = float(row.get('monthly_rent', '0'))
        except ValueError:
            row_errors.append(f'Row {line}: monthly_rent must be a number.')
            rent = 0

        if row_errors:
            errors.extend(row_errors)
            continue

        duration = int(row.get('plan_duration_months', 12) or 12)
        end_date = start + relativedelta(months=duration) if start else None

        records.append(Customer(
            cust_name=name,
            contact_number=phone,
            email_id=row.get('email_id', '').strip() or None,
            plan_name=plan_name,
            plan_duration_months=duration,
            plan_start_date=start,
            plan_end_date=end_date,
            monthly_rent=rent,
            payment_freq=row.get('payment_freq', 'Monthly').strip() or 'Monthly',
            deposit=float(row.get('deposit', 0) or 0),
            address=row.get('address', '').strip(),
            city=row.get('city', '').strip(),
            pin=row.get('pin', '').strip(),
            notes=row.get('notes', '').strip(),
            customer_status='Active',
            next_billing_date=start + relativedelta(months=1) if start else None,
        ))

    if errors:
        return {'success': False, 'errors': errors}

    try:
        db.session.bulk_save_objects(records)
        db.session.commit()
        return {'success': True, 'count': len(records)}
    except Exception as exc:
        db.session.rollback()
        return {'success': False, 'errors': [str(exc)]}
