"""
routes/dashboard_routes.py - Main dashboard with KPIs and charts.
"""
import json
from flask import Blueprint, render_template, jsonify
from flask_login import login_required
from services.dashboard_service import (
    get_dashboard_stats,
    get_monthly_collections,
    get_monthly_expenses_chart,
    get_recent_payments,
    get_overdue_customers,
)

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Render main dashboard."""
    stats = get_dashboard_stats()
    monthly_collections = get_monthly_collections(6)
    monthly_expenses = get_monthly_expenses_chart(6)
    recent_payments = get_recent_payments(8)
    overdue_customers = get_overdue_customers(8)

    return render_template(
        'dashboard.html',
        stats=stats,
        monthly_collections=json.dumps(monthly_collections),
        monthly_expenses=json.dumps(monthly_expenses),
        recent_payments=recent_payments,
        overdue_customers=overdue_customers,
        active_page='dashboard',
    )


@dashboard_bp.route('/api/stats')
@login_required
def api_stats():
    """AJAX endpoint for dashboard KPI refresh."""
    return jsonify(get_dashboard_stats())
