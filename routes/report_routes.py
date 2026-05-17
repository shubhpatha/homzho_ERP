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
from models.expense import Expense
from models.customer import Customer
from models.machine import Machine

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

    # ── Financial summary ────────────────────────────────────────────────────
    total_revenue = db.session.query(
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.payment_date >= start_date,
        Payment.payment_date <= end_date,
    ).scalar() or 0

    total_expenses = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
    ).scalar() or 0

    # ── Machine status distribution ──────────────────────────────────────────
    machine_status = db.session.query(
        Machine.machine_status,
        func.count(Machine.machine_id).label('count')
    ).group_by(Machine.machine_status).all()

    # ── Expense breakdown by category ────────────────────────────────────────
    expense_breakdown = db.session.query(
        Expense.expense_category,
        func.sum(Expense.amount).label('total')
    ).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
    ).group_by(Expense.expense_category).all()

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
        total_expenses=float(total_expenses),
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

    # Expenses in range
    expenses = Expense.query.filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
    ).order_by(Expense.expense_date).all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([f'Report: {start_date} to {end_date}'])
    writer.writerow([])

    writer.writerow(['--- PAYMENTS ---'])
    writer.writerow(['Date', 'Customer', 'Amount (₹)', 'Mode'])
    for p in payments:
        writer.writerow([p.payment_date, p.cust_name, p.amount_paid, p.payment_mode])

    writer.writerow([])
    writer.writerow(['--- EXPENSES ---'])
    writer.writerow(['Date', 'Category', 'Description', 'Amount (₹)'])
    for e in expenses:
        writer.writerow([e.expense_date, e.expense_category, e.description, e.amount])

    output.seek(0)
    filename = f'report_{start_date}_{end_date}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )
