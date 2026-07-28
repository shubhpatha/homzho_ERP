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
from services.accounting_service import sync_payment_to_ledger

payment_bp = Blueprint('payments', __name__, url_prefix='/payments')

PAYMENT_MODES = ['Cash', 'UPI', 'Bank Transfer', 'Cheque', 'Online']


def _parse_amount(value, default=0.0):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return default
    return max(amount, 0.0)


def _default_invoice_description(customer):
    if customer and customer.plan_name:
        return customer.plan_name
    return 'Water Purifier Rental Services'


def _build_invoice_items(form, customer):
    descriptions = form.getlist('item_description')
    quantities = form.getlist('item_quantity')
    unit_prices = form.getlist('item_unit_price')
    hsn_sac_codes = form.getlist('item_hsn_sac')
    row_count = max(len(descriptions), len(quantities), len(unit_prices))
    items = []

    for index in range(row_count):
        description = descriptions[index].strip() if index < len(descriptions) else ''
        quantity = _parse_amount(quantities[index] if index < len(quantities) else 1, 1.0)
        unit_price = _parse_amount(unit_prices[index] if index < len(unit_prices) else 0, 0.0)
        hsn_sac = (hsn_sac_codes[index].strip() if index < len(hsn_sac_codes) else '') or ''
        if not description and unit_price <= 0:
            continue
        if not description:
            description = 'Product / Service'
        if quantity <= 0:
            quantity = 1.0
        line_total = round(quantity * unit_price, 2)
        items.append({
            'description': description,
            'hsn_sac': hsn_sac,
            'quantity': quantity,
            'unit_price': unit_price,
            'line_total': line_total,
        })

    if not items:
        fallback_total = _parse_amount(form.get('amount_due'), customer.monthly_rent)
        items.append({
            'description': _default_invoice_description(customer),
            'hsn_sac': '',
            'quantity': 1.0,
            'unit_price': fallback_total,
            'line_total': round(fallback_total, 2),
        })

    return items


def _payment_status(amount_paid, amount_due):
    if amount_paid <= 0:
        return 'Pending'
    if amount_paid >= amount_due:
        return 'Paid'
    return 'Partial'


def _zero_gst_summary(amount):
    gross_amount = _parse_amount(amount)
    return {
        'gross_amount': gross_amount,
        'taxable_amount': gross_amount,
        'cgst_amount': 0.0,
        'sgst_amount': 0.0,
        'total_tax_amount': 0.0,
    }


def _invoice_summary(payment):
    deposit_amount = _parse_amount(payment.deposit_amount)
    is_gst_invoice = True if payment.is_gst_invoice is None else bool(payment.is_gst_invoice)
    invoice_items = payment.invoice_items
    if not invoice_items:
        fallback_total = max(_parse_amount(payment.amount_due or payment.amount_paid) - deposit_amount, 0.0)
        invoice_items = [{
            'description': _default_invoice_description(payment.customer),
            'quantity': 1.0,
            'unit_price': fallback_total,
            'line_total': round(fallback_total, 2),
        }]

    taxable_total = round(sum(_parse_amount(item.get('line_total')) for item in invoice_items), 2)
    invoice_tax = calculate_inclusive_gst(taxable_total) if is_gst_invoice else _zero_gst_summary(taxable_total)
    invoice_amount = round(taxable_total + deposit_amount, 2)
    balance_amount = round(max(invoice_amount - _parse_amount(payment.amount_paid), 0.0), 2)

    return {
        'is_gst_invoice': is_gst_invoice,
        'invoice_items': invoice_items,
        'deposit_amount': deposit_amount,
        'taxable_total': taxable_total,
        'invoice_tax': invoice_tax,
        'invoice_amount': invoice_amount,
        'balance_amount': balance_amount,
    }


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
            amount_paid = _parse_amount(request.form['amount_paid'])
            invoice_items = _build_invoice_items(request.form, customer)
            is_gst_invoice = request.form.get('invoice_tax_mode', 'gst') == 'gst'
            deposit_amount = (
                _parse_amount(request.form.get('deposit_amount'))
                if request.form.get('include_deposit')
                else 0.0
            )
            taxable_total = round(sum(item['line_total'] for item in invoice_items), 2)
            amount_due = round(taxable_total + deposit_amount, 2)

            invoice_no = generate_invoice_no(payment_date)

            # Calculate days overdue
            days_overdue = 0
            if customer.next_billing_date and payment_date > customer.next_billing_date:
                days_overdue = (payment_date - customer.next_billing_date).days

            # Determine baseline for calculations (payment_date or previous next_billing_date)
            # Default fallback for backwards compatibility is to use payment_date
            renew_from_expiry = request.form.get('renew_from_expiry') == '1'
            base_date = payment_date
            if renew_from_expiry and customer.next_billing_date:
                base_date = customer.next_billing_date

            # Calculate next due date from plan master when available.
            plan = Plan.query.filter_by(plan_name=customer.plan_name, is_active=True).first()
            if plan:
                next_due = base_date + timedelta(days=plan.validity_in_days)
            else:
                freq_months = {'Monthly': 1, 'Quarterly': 3, 'Half Yearly': 6, 'Annual': 12, 'Yearly': 12}
                months = freq_months.get(customer.payment_freq, 1)
                next_due = base_date + relativedelta(months=months)

            payment = Payment(
                customer_id=customer_id,
                payment_date=payment_date,
                amount_paid=amount_paid,
                amount_due=amount_due,
                deposit_amount=deposit_amount,
                is_gst_invoice=is_gst_invoice,
                payment_mode=request.form['payment_mode'],
                transaction_id=request.form.get('transaction_id', '').strip() or None,
                invoice_no=invoice_no,
                payment_status=_payment_status(amount_paid, amount_due),
                days_overdue=days_overdue,
                remark=request.form.get('remark', '').strip(),
                collected_by=request.form.get('collected_by', current_user.full_name or current_user.username),
                next_due_date=next_due,
            )
            payment.invoice_items = invoice_items
            db.session.add(payment)

            # Update customer next_billing_date, and also update rental plan start and end dates
            customer.next_billing_date = next_due
            customer.plan_start_date = base_date
            customer.plan_end_date = next_due
            
            db.session.flush()
            sync_payment_to_ledger(payment, current_user.username)

            db.session.commit()
            log_activity(current_user.username, 'Add', 'Payment', payment.payment_id,
                         f'Invoice {invoice_no} for customer #{customer_id} (Renewed from expiry: {renew_from_expiry})', request.remote_addr)
            flash(f'Payment recorded and Plan Renewed! Invoice: {invoice_no}', 'success')
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
    invoice = _invoice_summary(payment)
    return render_template(
        'payments/view.html',
        payment=payment,
        is_gst_invoice=invoice['is_gst_invoice'],
        invoice_items=invoice['invoice_items'],
        deposit_amount=invoice['deposit_amount'],
        taxable_total=invoice['taxable_total'],
        invoice_amount=invoice['invoice_amount'],
        invoice_tax=invoice['invoice_tax'],
        balance_amount=invoice['balance_amount'],
        active_page='payments',
    )


# ---------------------------------------------------------------------------
# Print / Download Invoice (standalone page, no sidebar)
# ---------------------------------------------------------------------------

@payment_bp.route('/<int:payment_id>/print')
@login_required
def print_invoice(payment_id):
    """Render a standalone, sidebar-free invoice page for print / PDF download."""
    if not current_user.has_permission('payments'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    payment = db.get_or_404(Payment, payment_id)
    invoice = _invoice_summary(payment)
    return render_template(
        'payments/invoice_print.html',
        payment=payment,
        is_gst_invoice=invoice['is_gst_invoice'],
        invoice_items=invoice['invoice_items'],
        deposit_amount=invoice['deposit_amount'],
        taxable_total=invoice['taxable_total'],
        invoice_amount=invoice['invoice_amount'],
        invoice_tax=invoice['invoice_tax'],
        balance_amount=invoice['balance_amount'],
    )


# ---------------------------------------------------------------------------
# Edit Payment
# ---------------------------------------------------------------------------

@payment_bp.route('/<int:payment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(payment_id):
    """Correct an existing payment — amount, items, mode, ref. Invoice no & next_due_date are frozen."""
    if not current_user.has_permission('payments'):
        flash('Access denied.', 'danger')
        return redirect(url_for('payments.index'))

    payment = db.get_or_404(Payment, payment_id)

    if request.method == 'POST':
        try:
            customer = payment.customer

            # Re-build invoice items (picks up hsn_sac too)
            invoice_items = _build_invoice_items(request.form, customer)
            is_gst_invoice = request.form.get('invoice_tax_mode', 'gst') == 'gst'
            deposit_amount = (
                _parse_amount(request.form.get('deposit_amount'))
                if request.form.get('include_deposit')
                else 0.0
            )
            taxable_total = round(sum(item['line_total'] for item in invoice_items), 2)
            amount_due = round(taxable_total + deposit_amount, 2)
            amount_paid = _parse_amount(request.form['amount_paid'])

            # Update fields — invoice_no and next_due_date are intentionally NOT changed
            payment.amount_paid = amount_paid
            payment.amount_due = amount_due
            payment.deposit_amount = deposit_amount
            payment.is_gst_invoice = is_gst_invoice
            payment.payment_mode = request.form['payment_mode']
            payment.transaction_id = request.form.get('transaction_id', '').strip() or None
            payment.remark = request.form.get('remark', '').strip()
            payment.collected_by = request.form.get('collected_by', '').strip()
            payment.payment_status = _payment_status(amount_paid, amount_due)
            payment.invoice_items = invoice_items

            # Sync updated amounts/mode/description to the general ledger
            # upsert_ledger_entry matches on source_type + source_id + entry_type + category
            # so this updates the existing ledger row in-place (reference_no = invoice_no stays the same)
            db.session.flush()
            sync_payment_to_ledger(payment, current_user.username)

            db.session.commit()
            log_activity(current_user.username, 'Edit', 'Payment', payment.payment_id,
                         f'Edited invoice {payment.invoice_no}', request.remote_addr)
            flash(f'Invoice {payment.invoice_no} updated successfully.', 'success')
            return redirect(url_for('payments.view', payment_id=payment.payment_id))

        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error editing payment: {exc}', exc_info=True)
            flash(f'Error updating payment: {exc}', 'danger')

    # Pre-build the invoice summary for form pre-fill
    invoice = _invoice_summary(payment)
    return render_template(
        'payments/edit.html',
        payment=payment,
        invoice=invoice,
        payment_modes=PAYMENT_MODES,
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
        'plan_name': customer.plan_name,
        'payment_freq': customer.payment_freq,
        'deposit': customer.deposit or 0,
        'machine_serial_no': customer.machine_serial_no or '',
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
