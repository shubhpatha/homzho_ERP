"""
routes/payment_routes.py - Payment CRUD, invoice generation, CSV export.
"""
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, Response, current_app, jsonify)
from flask_login import login_required, current_user
from extensions import db
from models.customer import Customer
from models.payment import Payment
from models.plan import Plan
from utils.helpers import log_activity, get_page_items, generate_invoice_no
from utils.tax import calculate_inclusive_gst

payment_bp = Blueprint('payments', __name__, url_prefix='/payments')

PAYMENT_MODES = ['Cash', 'UPI', 'Bank Transfer', 'Cheque', 'Online']


# ---------------------------------------------------------------------------
# List Payments
# ---------------------------------------------------------------------------

@payment_bp.route('/')
@login_required
def index():
    """Payment list with search and filters."""
    if not current_user.has_permission('payments'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    month_filter = request.args.get('month', '').strip()

    query = Payment.query.join(Customer)

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Customer.cust_name.ilike(like),
                Payment.invoice_no.ilike(like),
                Payment.transaction_id.ilike(like),
                Customer.contact_number.ilike(like),
            )
        )
    if status_filter:
        query = query.filter(Payment.payment_status == status_filter)
    if month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            query = query.filter(
                db.extract('year', Payment.payment_date) == year,
                db.extract('month', Payment.payment_date) == month,
            )
        except Exception:
            pass

    query = query.order_by(Payment.payment_date.desc())
    pagination = get_page_items(query, page)

    # Monthly summary totals
    today = date.today()
    first_of_month = today.replace(day=1)
    monthly_total = db.session.query(
        db.func.coalesce(db.func.sum(Payment.amount_paid), 0)
    ).filter(Payment.payment_date >= first_of_month).scalar() or 0

    return render_template(
        'payments/index.html',
        payments=pagination.items,
        pagination=pagination,
        search=search,
        status_filter=status_filter,
        month_filter=month_filter,
        monthly_total=monthly_total,
        active_page='payments',
    )


# ---------------------------------------------------------------------------
# Add Payment
# ---------------------------------------------------------------------------

@payment_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Record a new payment."""
    if not current_user.has_permission('payments'):
        flash('Access denied.', 'danger')
        return redirect(url_for('payments.index'))

    customers = Customer.query.filter_by(customer_status='Active').order_by(Customer.cust_name).all()
    prefill_customer_id = request.args.get('customer_id', type=int)

    if request.method == 'POST':
        try:
            customer_id = int(request.form['customer_id'])
            customer = db.get_or_404(Customer, customer_id)
            payment_date = date.fromisoformat(request.form['payment_date'])
            amount_paid = float(request.form['amount_paid'])
            amount_due = float(request.form.get('amount_due', customer.monthly_rent))

            invoice_no = generate_invoice_no(payment_date)

            # Calculate days overdue
            days_overdue = 0
            if customer.next_billing_date and payment_date > customer.next_billing_date:
                days_overdue = (payment_date - customer.next_billing_date).days

            # Calculate next due date from plan master when available.
            plan = Plan.query.filter_by(plan_name=customer.plan_name, is_active=True).first()
            if plan:
                next_due = payment_date + timedelta(days=plan.validity_in_days)
            else:
                freq_months = {'Monthly': 1, 'Quarterly': 3, 'Half Yearly': 6, 'Annual': 12, 'Yearly': 12}
                months = freq_months.get(customer.payment_freq, 1)
                next_due = payment_date + relativedelta(months=months)

            payment = Payment(
                customer_id=customer_id,
                payment_date=payment_date,
                amount_paid=amount_paid,
                amount_due=amount_due,
                payment_mode=request.form['payment_mode'],
                transaction_id=request.form.get('transaction_id', '').strip() or None,
                invoice_no=invoice_no,
                payment_status='Paid' if amount_paid >= amount_due else 'Partial',
                days_overdue=days_overdue,
                remark=request.form.get('remark', '').strip(),
                collected_by=request.form.get('collected_by', current_user.full_name or current_user.username),
                next_due_date=next_due,
            )
            db.session.add(payment)

            # Update customer next_billing_date
            customer.next_billing_date = next_due

            db.session.commit()
            log_activity(current_user.username, 'Add', 'Payment', payment.payment_id,
                         f'Invoice {invoice_no} for customer #{customer_id}', request.remote_addr)
            flash(f'Payment recorded! Invoice: {invoice_no}', 'success')
            return redirect(url_for('payments.view', payment_id=payment.payment_id))

        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding payment: {exc}', exc_info=True)
            flash(f'Error recording payment: {exc}', 'danger')

    return render_template(
        'payments/add.html',
        customers=customers,
        payment_modes=PAYMENT_MODES,
        prefill_customer_id=prefill_customer_id,
        payment_date_default=date.today().isoformat(),
        active_page='payments',
    )


# ---------------------------------------------------------------------------
# View Payment
# ---------------------------------------------------------------------------

@payment_bp.route('/<int:payment_id>')
@login_required
def view(payment_id):
    """View payment details / invoice."""
    if not current_user.has_permission('payments'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    payment = db.get_or_404(Payment, payment_id)
    invoice_amount = payment.amount_due or payment.amount_paid
    invoice_tax = calculate_inclusive_gst(invoice_amount)
    return render_template(
        'payments/view.html',
        payment=payment,
        invoice_amount=invoice_amount,
        invoice_tax=invoice_tax,
        active_page='payments',
    )


# ---------------------------------------------------------------------------
# AJAX: get customer due amount
# ---------------------------------------------------------------------------

@payment_bp.route('/api/customer/<int:cust_id>/due')
@login_required
def customer_due(cust_id):
    """Return customer's monthly rent and next billing date for AJAX pre-fill."""
    if not current_user.has_permission('payments'):
        return jsonify({}), 403

    customer = db.get_or_404(Customer, cust_id)
    return jsonify({
        'monthly_rent': customer.monthly_rent,
        'next_billing_date': customer.next_billing_date.isoformat() if customer.next_billing_date else '',
        'cust_name': customer.cust_name,
    })


# ---------------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------------

@payment_bp.route('/export/csv')
@login_required
def export_csv():
    if not current_user.has_permission('payments'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    from services.export_service import export_payments_csv
    return Response(
        export_payments_csv(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=payments.csv'},
    )


# ---------------------------------------------------------------------------
# Overdue Payments List
# ---------------------------------------------------------------------------

@payment_bp.route('/overdue')
@login_required
def overdue():
    """List all customers with overdue billing."""
    if not current_user.has_permission('payments'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    today = date.today()
    overdue_customers = (
        Customer.query
        .filter(Customer.customer_status == 'Active')
        .filter(Customer.next_billing_date < today)
        .order_by(Customer.next_billing_date.asc())
        .all()
    )
    return render_template('payments/overdue.html', customers=overdue_customers,
                           today=today, active_page='payments')
