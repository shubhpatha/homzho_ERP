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
from models.employee import Employee
from models.lead import Lead
from models.maintenance import Maintenance
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

    # ── Plan distribution (customers created in period) ───────────────────────
    plan_distribution = db.session.query(
        Customer.plan_name,
        func.count(Customer.cust_id).label('count')
    ).filter(
        func.date(Customer.created_at) >= start_date,
        func.date(Customer.created_at) <= end_date,
    ).group_by(Customer.plan_name).order_by(func.count(Customer.cust_id).desc()).all()

    # ── Installations by employee (filtered by installation_date) ────────────
    installations_by_emp = db.session.query(
        Employee.emp_name,
        func.count(Customer.cust_id).label('count')
    ).join(Customer, Customer.installed_by_emp_id == Employee.emp_id).filter(
        Customer.installation_date >= start_date,
        Customer.installation_date <= end_date,
    ).group_by(Employee.emp_id, Employee.emp_name).order_by(func.count(Customer.cust_id).desc()).all()

    # ── Lead conversions by staff (filtered by lead updated_at) ──────────────
    leads_converted_by = db.session.query(
        Lead.contacted_by,
        func.count(Lead.lead_id).label('count')
    ).filter(
        Lead.status == 'Converted',
        Lead.contacted_by != None,
        Lead.contacted_by != '',
        func.date(Lead.updated_at) >= start_date,
        func.date(Lead.updated_at) <= end_date,
    ).group_by(Lead.contacted_by).order_by(func.count(Lead.lead_id).desc()).all()

    # ── Services done by technician (filtered by service_date) ───────────────
    # Prefer the Employee name when linked; fall back to legacy technician_name text.
    services_by_tech_linked = db.session.query(
        Employee.emp_name.label('technician'),
        func.count(Maintenance.service_id).label('count')
    ).join(Maintenance, Maintenance.technician_emp_id == Employee.emp_id).filter(
        Maintenance.service_date >= start_date,
        Maintenance.service_date <= end_date,
    ).group_by(Employee.emp_id, Employee.emp_name).all()

    services_by_tech_legacy = db.session.query(
        Maintenance.technician_name.label('technician'),
        func.count(Maintenance.service_id).label('count')
    ).filter(
        Maintenance.technician_emp_id == None,
        Maintenance.technician_name != None,
        Maintenance.technician_name != '',
        Maintenance.service_date >= start_date,
        Maintenance.service_date <= end_date,
    ).group_by(Maintenance.technician_name).all()

    # Merge the two result sets into one list sorted by count desc.
    tech_map = {}
    for row in services_by_tech_linked:
        tech_map[row.technician] = tech_map.get(row.technician, 0) + row.count
    for row in services_by_tech_legacy:
        tech_map[row.technician] = tech_map.get(row.technician, 0) + row.count
    services_by_tech = sorted(
        [{'name': k, 'count': v} for k, v in tech_map.items()],
        key=lambda x: x['count'], reverse=True
    )

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
        plan_distribution=plan_distribution,
        installations_by_emp=installations_by_emp,
        leads_converted_by=leads_converted_by,
        services_by_tech=services_by_tech,
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
