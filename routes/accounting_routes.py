"""
routes/accounting_routes.py - Unified account ledger views and exports.
"""
import csv
import io
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from extensions import db
from models.accounting import AccountLedger
from services.accounting_service import ledger_total, ledger_breakdown
from utils.helpers import get_page_items

accounting_bp = Blueprint('accounting', __name__, url_prefix='/accounting')


@accounting_bp.route('/')
@login_required
def index():
    """Unified income and expense ledger."""
    if not current_user.has_permission('accounting'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type', '').strip()
    category_filter = request.args.get('category', '').strip()
    month_filter = request.args.get('month', '').strip()

    query = AccountLedger.query
    if type_filter:
        query = query.filter(AccountLedger.entry_type == type_filter)
    if category_filter:
        query = query.filter(AccountLedger.category == category_filter)
    if month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            query = query.filter(
                db.extract('year', AccountLedger.entry_date) == year,
                db.extract('month', AccountLedger.entry_date) == month,
            )
        except Exception:
            pass

    query = query.order_by(AccountLedger.entry_date.desc(), AccountLedger.ledger_id.desc())
    pagination = get_page_items(query, page)

    today = date.today()
    first_of_month = today.replace(day=1)
    monthly_income = ledger_total('Income', first_of_month)
    monthly_expense = ledger_total('Expense', first_of_month)
    category_totals = ledger_breakdown('Expense', first_of_month, today)
    categories = [row[0] for row in db.session.query(AccountLedger.category).distinct().order_by(AccountLedger.category).all()]

    return render_template(
        'accounting/index.html',
        entries=pagination.items,
        pagination=pagination,
        type_filter=type_filter,
        category_filter=category_filter,
        month_filter=month_filter,
        categories=categories,
        monthly_income=monthly_income,
        monthly_expense=monthly_expense,
        monthly_net=monthly_income - monthly_expense,
        category_totals=category_totals,
        active_page='accounting',
    )


@accounting_bp.route('/export/csv')
@login_required
def export_csv():
    """Export account ledger as CSV."""
    if not current_user.has_permission('accounting'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    entries = AccountLedger.query.order_by(AccountLedger.entry_date.desc(), AccountLedger.ledger_id.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Type', 'Category', 'Amount', 'Mode', 'Party', 'Description', 'Source', 'Source ID', 'Reference', 'Created By'])
    for entry in entries:
        writer.writerow([
            entry.entry_date,
            entry.entry_type,
            entry.category,
            entry.amount,
            entry.payment_mode,
            entry.party_name,
            entry.description,
            entry.source_type,
            entry.source_id,
            entry.reference_no,
            entry.created_by,
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=account_ledger.csv'},
    )