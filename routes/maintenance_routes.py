"""
routes/maintenance_routes.py - Maintenance record CRUD with image uploads.
"""
from datetime import date, timedelta
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, Response, current_app)
from flask_login import login_required, current_user
from extensions import db
from models.machine import Machine
from models.maintenance import Maintenance
from utils.helpers import log_activity, get_page_items
from utils.file_handler import save_upload
from services.accounting_service import sync_maintenance_to_ledger

maintenance_bp = Blueprint('maintenance', __name__, url_prefix='/maintenance')

SERVICE_TYPES = ['Routine Service', 'Filter Change', 'Repair', 'Installation Check',
                 'Emergency', 'Warranty Service']
FEEDBACK_OPTIONS = ['Excellent', 'Good', 'Average', 'Poor']


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

    if request.method == 'POST':
        try:
            machine_id_raw = request.form.get('machine_id', '').strip()
            if not machine_id_raw:
                flash('Please select a machine before saving the service record.', 'danger')
                return render_template(
                    'maintenance/add.html',
                    machines=machines,
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
            next_service = service_date + timedelta(days=90)

            record = Maintenance(
                machine_id=machine_id,
                customer_id=request.form.get('customer_id') or None,
                service_date=service_date,
                next_service_date=next_service,
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

            db.session.flush()
            sync_maintenance_to_ledger(record, current_user.username)
            db.session.commit()
            log_activity(current_user.username, 'Add', 'Maintenance', record.service_id,
                         f'Maintenance for machine #{machine_id}', request.remote_addr)
            flash('Maintenance record added!', 'success')
            return redirect(url_for('maintenance.index'))

        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding maintenance: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    return render_template(
        'maintenance/add.html',
        machines=machines,
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
