"""
routes/expense_routes.py - Expense management with bill image uploads.
"""
from datetime import date
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, Response, current_app)
from flask_login import login_required, current_user
from extensions import db
from models.expense import Expense
from utils.helpers import log_activity, get_page_items
from utils.file_handler import save_upload
from services.accounting_service import sync_expense_to_ledger

expense_bp = Blueprint('expenses', __name__, url_prefix='/expenses')

CATEGORIES = ['Fuel', 'Technician', 'Marketing', 'Office', 'Repair', 'Misc']
PAYMENT_MODES = ['Cash', 'UPI', 'Bank Transfer', 'Cheque']


@expense_bp.route('/')
@login_required
def index():
    """Expense list with filters."""
    if not current_user.has_permission('expenses'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    page = request.args.get('page', 1, type=int)
    category_filter = request.args.get('category', '').strip()
    month_filter = request.args.get('month', '').strip()

    query = Expense.query
    if category_filter:
        query = query.filter(Expense.expense_category == category_filter)
    if month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            query = query.filter(
                db.extract('year', Expense.expense_date) == year,
                db.extract('month', Expense.expense_date) == month,
            )
        except Exception:
            pass

    query = query.order_by(Expense.expense_date.desc())
    pagination = get_page_items(query, page)

    # Monthly total
    today = date.today()
    monthly_total = db.session.query(
        db.func.coalesce(db.func.sum(Expense.amount), 0)
    ).filter(
        Expense.expense_date >= today.replace(day=1)
    ).scalar() or 0

    # Category totals for current month
    from sqlalchemy import func
    cat_totals = db.session.query(
        Expense.expense_category,
        func.sum(Expense.amount).label('total')
    ).filter(
        Expense.expense_date >= today.replace(day=1)
    ).group_by(Expense.expense_category).all()

    return render_template(
        'expenses/index.html',
        expenses=pagination.items,
        pagination=pagination,
        category_filter=category_filter,
        month_filter=month_filter,
        categories=CATEGORIES,
        monthly_total=monthly_total,
        cat_totals=cat_totals,
        active_page='expenses',
    )


@expense_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add expense record with optional bill image."""
    if not current_user.has_permission('expenses'):
        flash('Access denied.', 'danger')
        return redirect(url_for('expenses.index'))

    if request.method == 'POST':
        try:
            expense = Expense(
                expense_date=date.fromisoformat(request.form['expense_date']),
                expense_category=request.form['expense_category'],
                amount=float(request.form['amount']),
                payment_mode=request.form['payment_mode'],
                paid_to=request.form.get('paid_to', '').strip(),
                remarks=request.form.get('remarks', '').strip(),
                approved_by=request.form.get('approved_by', '').strip(),
            )

            bill_image = request.files.get('bill_image')
            if bill_image and bill_image.filename:
                try:
                    rel_path = save_upload(bill_image, 'expenses')
                    expense.bill_image = rel_path
                except ValueError as ve:
                    flash(f'Bill image skipped: {ve}', 'warning')

            db.session.add(expense)
            db.session.flush()
            sync_expense_to_ledger(expense, current_user.username)
            db.session.commit()
            log_activity(current_user.username, 'Add', 'Expense', expense.expense_id,
                         f'Expense {expense.expense_category} ₹{expense.amount}', request.remote_addr)
            flash('Expense recorded!', 'success')
            return redirect(url_for('expenses.index'))

        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding expense: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    return render_template(
        'expenses/add.html',
        categories=CATEGORIES,
        payment_modes=PAYMENT_MODES,
        expense_date_default=date.today().isoformat(),
        active_page='expenses',
    )


@expense_bp.route('/export/csv')
@login_required
def export_csv():
    if not current_user.has_permission('expenses'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    from services.export_service import export_expenses_csv
    return Response(
        export_expenses_csv(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=expenses.csv'},
    )
