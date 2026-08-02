"""
routes/maintenance_routes.py - Maintenance record CRUD with image uploads.
"""
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, Response, current_app, jsonify)
from flask_login import login_required, current_user
from extensions import db
from models.machine import Machine
from models.maintenance import Maintenance
from models.inventory import InventoryItem
from models.employee import Employee
from utils.helpers import log_activity, get_page_items
from utils.file_handler import save_upload
from services.accounting_service import sync_maintenance_to_ledger
from services.maintenance_service import deduct_inventory_for_maintenance

maintenance_bp = Blueprint('maintenance', __name__, url_prefix='/maintenance')

SERVICE_TYPES = ['Routine Service', 'Filter Change', 'Repair', 'Installation Check',
                 'Emergency', 'Warranty Service']
FEEDBACK_OPTIONS = ['Excellent', 'Good', 'Average', 'Poor']
# Stock level below which a low-stock warning badge is shown in the UI
LOW_STOCK_THRESHOLD = 10


# ---------------------------------------------------------------------------
# AJAX: Inventory items list (for the maintenance form parts picker)
# ---------------------------------------------------------------------------

@maintenance_bp.route('/api/inventory-items')
@login_required
def api_inventory_items():
    """Return all active inventory items as JSON for the maintenance form.

    Response shape:
      [{id, name, category, unit, current_stock, is_low_stock}, ...]

    is_low_stock is True when current_stock < LOW_STOCK_THRESHOLD (default 10).
    This drives the orange warning badge shown next to the dropdown in the UI.
    """
    items = InventoryItem.query.filter_by(is_active=True).order_by(InventoryItem.item_name).all()
    return jsonify([
        {
            'id': item.item_id,
            'name': item.item_name,
            'category': item.category,
            'unit': item.unit,
            'unit_cost': float(item.unit_cost or 0),
            'current_stock': float(item.current_stock or 0),
            'is_low_stock': float(item.current_stock or 0) < LOW_STOCK_THRESHOLD,
        }
        for item in items
    ])



@maintenance_bp.route('/')
@login_required
def index():
    """Maintenance records list."""
    if not current_user.has_permission('maintenance'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    technician_filter = request.args.get('technician', '').strip()

    query = Maintenance.query.join(Machine)

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Machine.machine_serial_no.ilike(like),
                Maintenance.technician_name.ilike(like),
                Maintenance.service_type.ilike(like),
            )
        )
    if technician_filter:
        query = query.filter(Maintenance.technician_name.ilike(f'%{technician_filter}%'))

    query = query.order_by(Maintenance.service_date.desc())
    pagination = get_page_items(query, page)

    # Due alerts
    today = date.today()
    due_7 = Machine.query.filter(
        Machine.machine_status == 'Installed',
        Machine.next_service_date <= today + timedelta(days=7),
        Machine.next_service_date >= today,
    ).count()
    overdue_count = Machine.query.filter(
        Machine.machine_status == 'Installed',
        Machine.next_service_date < today,
    ).count()

    technicians = [r[0] for r in
                   db.session.query(Maintenance.technician_name).distinct().all() if r[0]]

    return render_template(
        'maintenance/index.html',
        records=pagination.items,
        pagination=pagination,
        search=search,
        technician_filter=technician_filter,
        technicians=technicians,
        due_7=due_7,
        overdue_count=overdue_count,
        active_page='maintenance',
    )


@maintenance_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add maintenance record."""
    if not current_user.has_permission('maintenance'):
        flash('Access denied.', 'danger')
        return redirect(url_for('maintenance.index'))

    machines = Machine.query.filter(Machine.machine_status.in_(['Installed', 'Under Maintenance'])).all()
    prefill_machine_id = request.args.get('machine_id', type=int)
    # Only allow assignment to existing active employees
    technicians = Employee.query.filter(
        Employee.status == 'Active',
        Employee.emp_type.in_(['Field Technician', 'Manager', 'Other'])
    ).order_by(Employee.emp_name).all()

    if request.method == 'POST':
        try:
            machine_id_raw = request.form.get('machine_id', '').strip()
            if not machine_id_raw:
                flash('Please select a machine before saving the service record.', 'danger')
                return render_template(
                    'maintenance/add.html',
                    machines=machines,
                    technicians=technicians,
                    service_types=SERVICE_TYPES,
                    feedback_options=FEEDBACK_OPTIONS,
                    service_date_default=request.form.get('service_date') or date.today().isoformat(),
                    prefill_machine_id=None,
                    active_page='maintenance',
                )

            machine_id = int(machine_id_raw)
            machine = db.session.get(Machine, machine_id)
            if not machine:
                flash('Selected machine was not found.', 'danger')
                return redirect(url_for('maintenance.add'))

            service_date = date.fromisoformat(request.form['service_date'])
            # Read interval chosen by the technician (default 3 months)
            next_svc_months = int(request.form.get('next_service_months') or 3)
            next_service = service_date + relativedelta(months=next_svc_months)

            record = Maintenance(
                machine_id=machine_id,
                customer_id=request.form.get('customer_id') or None,
                service_date=service_date,
                next_service_date=next_service,
                next_service_months=next_svc_months,
                service_type=request.form['service_type'],
                parts_replaced=request.form.get('parts_replaced', '').strip(),
                filter_changed=bool(request.form.get('filter_changed')),
                technician_name=request.form.get('technician_name', '').strip(),
                water_tds=float(request.form['water_tds']) if request.form.get('water_tds') else None,
                main_exp=float(request.form.get('main_exp', 0) or 0),
                travel_exp=float(request.form.get('travel_exp', 0) or 0),
                customer_feedback=request.form.get('customer_feedback', ''),
                remark=request.form.get('remark', '').strip(),
            )

            # Link technician to employee if selected from dropdown
            tech_emp_id_raw = request.form.get('technician_emp_id', '').strip()
            if tech_emp_id_raw and tech_emp_id_raw.isdigit():
                tech_emp = db.session.get(Employee, int(tech_emp_id_raw))
                if tech_emp:
                    record.technician_emp_id = tech_emp.emp_id
                    record.technician_name = tech_emp.emp_name  # keep text field in sync

            # Handle image upload
            image = request.files.get('service_image')
            if image and image.filename:
                try:
                    rel_path = save_upload(image, f'maintenance/machine_{machine_id}')
                    record.image_path = rel_path
                except ValueError as ve:
                    flash(f'Image upload skipped: {ve}', 'warning')

            db.session.add(record)

            # Update machine service dates
            if machine:
                machine.last_service_date = service_date
                machine.next_service_date = next_service

            db.session.flush()  # assigns record.service_id before ledger + inventory
            sync_maintenance_to_ledger(record, current_user.username)

            # ── Inventory deduction ─────────────────────────────────────────
            # Collect part_item_id[] / part_qty[] arrays posted from the form.
            # Rows with empty item_id or zero quantity are silently skipped
            # inside deduct_inventory_for_maintenance().
            part_ids  = request.form.getlist('part_item_id')
            part_qtys = request.form.getlist('part_qty')

            parts_list = []
            for pid, pqty in zip(part_ids, part_qtys):
                try:
                    item_id  = int(pid) if pid and pid.strip() else None
                    quantity = float(pqty) if pqty and pqty.strip() else 0
                except (ValueError, TypeError):
                    item_id, quantity = None, 0
                if item_id and quantity > 0:
                    parts_list.append({'item_id': item_id, 'quantity': quantity})

            inv_warnings = deduct_inventory_for_maintenance(
                service_record=record,
                parts_list=parts_list,
                created_by=current_user.username,
            )
            # ───────────────────────────────────────────────────────────────

            db.session.commit()
            log_activity(current_user.username, 'Add', 'Maintenance', record.service_id,
                         f'Maintenance for machine #{machine_id}', request.remote_addr)

            # Flash any inventory stock warnings collected during deduction
            for warn in inv_warnings:
                flash(f'⚠️ Stock warning: {warn}', 'warning')

            flash('Maintenance record added!', 'success')
            return redirect(url_for('maintenance.index'))

        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding maintenance: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    return render_template(
        'maintenance/add.html',
        machines=machines,
        technicians=technicians,
        service_types=SERVICE_TYPES,
        feedback_options=FEEDBACK_OPTIONS,
        service_date_default=date.today().isoformat(),
        prefill_machine_id=prefill_machine_id,
        active_page='maintenance',
    )


@maintenance_bp.route('/due')
@login_required
def due():
    """Upcoming and overdue maintenance list."""
    if not current_user.has_permission('maintenance'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    today = date.today()
    due_7 = Machine.query.filter(
        Machine.machine_status == 'Installed',
        Machine.next_service_date <= today + timedelta(days=7),
        Machine.next_service_date >= today,
    ).all()
    due_15 = Machine.query.filter(
        Machine.machine_status == 'Installed',
        Machine.next_service_date <= today + timedelta(days=15),
        Machine.next_service_date > today + timedelta(days=7),
    ).all()
    overdue = Machine.query.filter(
        Machine.machine_status == 'Installed',
        Machine.next_service_date < today,
    ).order_by(Machine.next_service_date.asc()).all()

    return render_template(
        'maintenance/due.html',
        due_7=due_7,
        due_15=due_15,
        overdue=overdue,
        today=today,
        active_page='maintenance',
    )


@maintenance_bp.route('/export/csv')
@login_required
def export_csv():
    if not current_user.has_permission('maintenance'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    from services.export_service import export_maintenance_csv
    return Response(
        export_maintenance_csv(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=maintenance.csv'},
    )
