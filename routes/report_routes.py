"""
routes/report_routes.py - Analytics reports and CSV downloads.
"""
import csv
import io
from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from sqlalchemy import func
from extensions import db
from models.payment import Payment
from models.accounting import AccountLedger
from models.customer import Customer
from models.machine import Machine
from utils.tax import calculate_inclusive_gst
from services.accounting_service import ledger_total, ledger_breakdown

report_bp = Blueprint('reports', __name__, url_prefix='/reports')


def _get_date_range():
    """Parse start_date / end_date from query-string, defaulting to current month."""
    today = date.today()
    default_start = today.replace(day=1)
    default_end = today

    try:
        start_date = date.fromisoformat(request.args.get('start_date', ''))
    except (ValueError, TypeError):
        start_date = default_start

    try:
        end_date = date.fromisoformat(request.args.get('end_date', ''))
    except (ValueError, TypeError):
        end_date = default_end

    return start_date, end_date


@report_bp.route('/')
@login_required
def index():
    """Reports overview page."""
    if not current_user.has_permission('reports'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    start_date, end_date = _get_date_range()

    # Financial summary from unified accounting ledger.
    total_revenue = ledger_total('Income', start_date, end_date)
    revenue_tax = calculate_inclusive_gst(total_revenue)

    total_expenses = ledger_total('Expense', start_date, end_date)
    net_profit = revenue_tax['taxable_amount'] - float(total_expenses)

    # ── Machine status distribution ──────────────────────────────────────────
    machine_status = db.session.query(
        Machine.machine_status,
        func.count(Machine.machine_id).label('count')
    ).group_by(Machine.machine_status).all()

    # Expense breakdown by category.
    expense_breakdown = ledger_breakdown('Expense', start_date, end_date)

    # ── New customers in period ──────────────────────────────────────────────
    new_customers = Customer.query.filter(
        func.date(Customer.created_at) >= start_date,
        func.date(Customer.created_at) <= end_date,
    ).count()

    # ── Cancelled customers in period ────────────────────────────────────────
    cancelled_customers = Customer.query.filter(
        Customer.customer_status == 'Cancelled',
        Customer.contract_end_date >= start_date,
        Customer.contract_end_date <= end_date,
    ).count()

    return render_template(
        'reports.html',
        start_date=start_date,
        end_date=end_date,
        total_revenue=float(total_revenue),
        taxable_revenue=revenue_tax['taxable_amount'],
        total_cgst=revenue_tax['cgst_amount'],
        total_sgst=revenue_tax['sgst_amount'],
        total_tax_paid=revenue_tax['total_tax_amount'],
        total_expenses=float(total_expenses),
        net_profit=net_profit,
        machine_status=machine_status,
        expense_breakdown=expense_breakdown,
        new_customers=new_customers,
        cancelled_customers=cancelled_customers,
        active_page='reports',
    )


@report_bp.route('/export')
@login_required
def export_summary():
    """Export financial summary as CSV."""
    if not current_user.has_permission('reports'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    start_date, end_date = _get_date_range()

    # Payments in range
    payments = db.session.query(
        Payment.payment_date,
        Customer.cust_name,
        Payment.amount_paid,
        Payment.payment_mode,
    ).join(Customer, Customer.cust_id == Payment.customer_id).filter(
        Payment.payment_date >= start_date,
        Payment.payment_date <= end_date,
    ).order_by(Payment.payment_date).all()

    accounting_entries = AccountLedger.query.filter(
        AccountLedger.entry_date >= start_date,
        AccountLedger.entry_date <= end_date,
    ).order_by(AccountLedger.entry_date, AccountLedger.ledger_id).all()

    total_revenue = ledger_total('Income', start_date, end_date)
    total_expenses = ledger_total('Expense', start_date, end_date)
    revenue_tax = calculate_inclusive_gst(total_revenue)
    net_profit = revenue_tax['taxable_amount'] - total_expenses

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([f'Report: {start_date} to {end_date}'])
    writer.writerow([])

    writer.writerow(['--- SUMMARY ---'])
    writer.writerow(['Gross Collections', total_revenue])
    writer.writerow(['Taxable Revenue', round(revenue_tax['taxable_amount'], 2)])
    writer.writerow(['CGST 9%', round(revenue_tax['cgst_amount'], 2)])
    writer.writerow(['SGST 9%', round(revenue_tax['sgst_amount'], 2)])
    writer.writerow(['Total GST Paid', round(revenue_tax['total_tax_amount'], 2)])
    writer.writerow(['Total Expenses', total_expenses])
    writer.writerow(['Net Profit After GST and Expenses', round(net_profit, 2)])
    writer.writerow([])

    writer.writerow(['--- PAYMENTS ---'])
    writer.writerow(['Date', 'Customer', 'Gross Amount', 'Taxable Amount', 'CGST 9%', 'SGST 9%', 'Mode'])
    for p in payments:
        payment_tax = calculate_inclusive_gst(p.amount_paid)
        writer.writerow([
            p.payment_date,
            p.cust_name,
            p.amount_paid,
            round(payment_tax['taxable_amount'], 2),
            round(payment_tax['cgst_amount'], 2),
            round(payment_tax['sgst_amount'], 2),
            p.payment_mode,
        ])

    writer.writerow([])
    writer.writerow(['--- ACCOUNT LEDGER ---'])
    writer.writerow(['Date', 'Type', 'Category', 'Party', 'Description', 'Source', 'Reference', 'Mode', 'Amount'])
    for entry in accounting_entries:
        writer.writerow([
            entry.entry_date,
            entry.entry_type,
            entry.category,
            entry.party_name,
            entry.description,
            entry.source_type,
            entry.reference_no,
            entry.payment_mode,
            entry.amount,
        ])

    output.seek(0)
    filename = f'report_{start_date}_{end_date}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )
