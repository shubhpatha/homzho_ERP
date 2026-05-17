"""
routes/reminder_routes.py - Billing and maintenance reminder dashboard.
"""
from datetime import date
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, jsonify, current_app)
from flask_login import login_required, current_user
from extensions import db
from models.reminder_log import ReminderLog
from services.billing_service import get_billing_reminders, get_overdue_payments, mark_reminder_sent
from services.maintenance_service import get_maintenance_due, get_overdue_maintenance, mark_maintenance_reminder_sent

reminder_bp = Blueprint('reminders', __name__, url_prefix='/reminders')


@reminder_bp.route('/')
@login_required
def index():
    """Reminders dashboard showing billing and maintenance due items."""
    days = request.args.get('days', 30, type=int)

    billing_upcoming = get_billing_reminders(days)
    billing_overdue = get_overdue_payments()
    maintenance_upcoming = get_maintenance_due(days)
    maintenance_overdue = get_overdue_maintenance()

    # Recent reminder history
    recent_logs = ReminderLog.query.order_by(ReminderLog.created_at.desc()).limit(20).all()

    return render_template(
        'reminders.html',
        billing_upcoming=billing_upcoming,
        billing_overdue=billing_overdue,
        maintenance_upcoming=maintenance_upcoming,
        maintenance_overdue=maintenance_overdue,
        recent_logs=recent_logs,
        days=days,
        today=date.today(),
        active_page='reminders',
    )


@reminder_bp.route('/mark-billing/<int:customer_id>', methods=['POST'])
@login_required
def mark_billing_sent(customer_id):
    """Mark billing reminder as sent for a customer."""
    try:
        mark_reminder_sent(customer_id, 'Billing', current_user.username)
        flash('Billing reminder marked as sent.', 'success')
    except Exception as exc:
        current_app.logger.error(f'Error marking billing reminder: {exc}', exc_info=True)
        flash(f'Error: {exc}', 'danger')
    return redirect(url_for('reminders.index'))


@reminder_bp.route('/mark-maintenance/<int:machine_id>', methods=['POST'])
@login_required
def mark_maintenance_sent(machine_id):
    """Mark maintenance reminder as sent for a machine."""
    try:
        mark_maintenance_reminder_sent(machine_id, current_user.username)
        flash('Maintenance reminder marked as sent.', 'success')
    except Exception as exc:
        current_app.logger.error(f'Error marking maintenance reminder: {exc}', exc_info=True)
        flash(f'Error: {exc}', 'danger')
    return redirect(url_for('reminders.index'))
