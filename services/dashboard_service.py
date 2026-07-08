"""
services/dashboard_service.py - Data aggregation for the dashboard.
"""
from datetime import date, timedelta
from models.customer import Customer
from models.machine import Machine
from models.payment import Payment
from utils.tax import calculate_inclusive_gst
from services.accounting_service import ledger_total


def get_dashboard_stats() -> dict:
    """Return all KPI counts and totals for the dashboard."""
    today = date.today()
    first_of_month = today.replace(day=1)

    total_customers = Customer.query.count()
    active_customers = Customer.query.filter_by(customer_status='Active').count()
    total_machines = Machine.query.count()
    available_machines = Machine.query.filter_by(machine_status='Available').count()

    # Pending collections: customers whose next_billing_date <= today and status Active
    pending_billing = (
        Customer.query
        .filter(Customer.customer_status == 'Active')
        .filter(Customer.next_billing_date <= today)
        .count()
    )

    # Overdue billing (> 7 days overdue)
    overdue_date = today - timedelta(days=7)
    overdue_billing = (
        Customer.query
        .filter(Customer.customer_status == 'Active')
        .filter(Customer.next_billing_date < overdue_date)
        .count()
    )

    # Upcoming maintenance in next 30 days
    upcoming_maintenance = (
        Machine.query
        .filter(Machine.machine_status == 'Installed')
        .filter(Machine.next_service_date <= today + timedelta(days=30))
        .filter(Machine.next_service_date >= today)
        .count()
    )

    # Monthly collections and expenses come from the unified ledger.
    monthly_revenue = ledger_total('Income', first_of_month)
    monthly_tax = calculate_inclusive_gst(monthly_revenue)

    monthly_expenses = ledger_total('Expense', first_of_month)
    monthly_net_profit = monthly_tax['taxable_amount'] - float(monthly_expenses)

    return {
        'total_customers': total_customers,
        'active_customers': active_customers,
        'total_machines': total_machines,
        'available_machines': available_machines,
        'pending_billing': pending_billing,
        'overdue_billing': overdue_billing,
        'upcoming_maintenance': upcoming_maintenance,
        'monthly_revenue': round(float(monthly_revenue), 2),
        'monthly_taxable_revenue': round(monthly_tax['taxable_amount'], 2),
        'monthly_cgst': round(monthly_tax['cgst_amount'], 2),
        'monthly_sgst': round(monthly_tax['sgst_amount'], 2),
        'monthly_tax_paid': round(monthly_tax['total_tax_amount'], 2),
        'monthly_expenses': round(float(monthly_expenses), 2),
        'monthly_net_profit': round(monthly_net_profit, 2),
    }


def get_monthly_collections(months: int = 6) -> list:
    """Return monthly collection totals for Chart.js."""
    today = date.today()
    result = []
    for i in range(months - 1, -1, -1):
        target = today.replace(day=1) - timedelta(days=30 * i)
        month_start = target.replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1)

        total = ledger_total('Income', month_start, month_end - timedelta(days=1))
        tax = calculate_inclusive_gst(total)

        result.append({
            'month': month_start.strftime('%b %Y'),
            'total': round(float(total), 2),
            'taxable': round(tax['taxable_amount'], 2),
            'tax_paid': round(tax['total_tax_amount'], 2),
        })
    return result


def get_monthly_expenses_chart(months: int = 6) -> list:
    """Return monthly expense totals for Chart.js."""
    today = date.today()
    result = []
    for i in range(months - 1, -1, -1):
        target = today.replace(day=1) - timedelta(days=30 * i)
        month_start = target.replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1)

        total = ledger_total('Expense', month_start, month_end - timedelta(days=1))

        result.append({
            'month': month_start.strftime('%b %Y'),
            'total': round(float(total), 2),
        })
    return result


def get_recent_payments(limit: int = 10) -> list:
    """Return recent payments for dashboard."""
    return (
        Payment.query
        .order_by(Payment.payment_date.desc())
        .limit(limit)
        .all()
    )


def get_overdue_customers(limit: int = 10) -> list:
    """Return customers with overdue billing."""
    today = date.today()
    return (
        Customer.query
        .filter(Customer.customer_status == 'Active')
        .filter(Customer.next_billing_date < today)
        .order_by(Customer.next_billing_date.asc())
        .limit(limit)
        .all()
    )
