"""
routes/machine_routes.py - Machine inventory, assignment, and service history.
"""
from datetime import date
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, Response, current_app)
from flask_login import login_required, current_user
from extensions import db
from models.machine import Machine, MachineAssignmentHistory
from models.customer import Customer
from utils.helpers import log_activity, get_page_items

machine_bp = Blueprint('machines', __name__, url_prefix='/machines')

MACHINE_STATUSES = ['Available', 'Installed', 'Under Maintenance', 'Scrapped']
MACHINE_CONDITIONS = ['Good', 'Fair', 'Poor']


@machine_bp.route('/')
@login_required
def index():
    """Machine inventory list."""
    if not current_user.has_permission('machines'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()

    query = Machine.query

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Machine.machine_serial_no.ilike(like),
                Machine.model_name.ilike(like),
            )
        )
    if status_filter:
        query = query.filter(Machine.machine_status == status_filter)

    query = query.order_by(Machine.created_at.desc())
    pagination = get_page_items(query, page)

    counts = {
        'total': Machine.query.count(),
        'available': Machine.query.filter_by(machine_status='Available').count(),
        'installed': Machine.query.filter_by(machine_status='Installed').count(),
        'maintenance': Machine.query.filter_by(machine_status='Under Maintenance').count(),
    }

    return render_template(
        'machines/index.html',
        machines=pagination.items,
        pagination=pagination,
        search=search,
        status_filter=status_filter,
        counts=counts,
        active_page='machines',
    )


@machine_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add a new machine."""
    if not current_user.has_permission('machines'):
        flash('Access denied.', 'danger')
        return redirect(url_for('machines.index'))

    if request.method == 'POST':
        try:
            serial_no = request.form['machine_serial_no'].strip()
            if Machine.query.filter_by(machine_serial_no=serial_no).first():
                flash(f'Machine serial number "{serial_no}" already exists.', 'danger')
                return render_template('machines/add.html', statuses=MACHINE_STATUSES,
                                       conditions=MACHINE_CONDITIONS, active_page='machines')

            machine = Machine(
                machine_serial_no=serial_no,
                model_name=request.form['model_name'].strip(),
                machine_status=request.form.get('machine_status', 'Available'),
                machine_condition=request.form.get('machine_condition', 'Good'),
                tds_level=float(request.form['tds_level']) if request.form.get('tds_level') else None,
                remarks=request.form.get('remarks', '').strip(),
            )
            db.session.add(machine)
            db.session.commit()
            log_activity(current_user.username, 'Add', 'Machine', machine.machine_id,
                         f'Added machine: {machine.machine_serial_no}', request.remote_addr)
            flash(f'Machine "{machine.machine_serial_no}" added!', 'success')
            return redirect(url_for('machines.view', machine_id=machine.machine_id))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding machine: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    return render_template('machines/add.html', statuses=MACHINE_STATUSES,
                           conditions=MACHINE_CONDITIONS, active_page='machines')


@machine_bp.route('/<int:machine_id>')
@login_required
def view(machine_id):
    """Machine detail page with service and assignment history."""
    if not current_user.has_permission('machines'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    machine = db.get_or_404(Machine, machine_id)
    maintenance_records = machine.maintenance_records.order_by(
        db.desc('service_date')).all()
    assignment_history = machine.assignment_history.order_by(
        db.desc('assigned_on')).all()
    return render_template(
        'machines/view.html',
        machine=machine,
        maintenance_records=maintenance_records,
        assignment_history=assignment_history,
        active_page='machines',
    )


@machine_bp.route('/<int:machine_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(machine_id):
    """Edit machine details."""
    if not current_user.has_permission('machines'):
        flash('Access denied.', 'danger')
        return redirect(url_for('machines.index'))

    machine = db.get_or_404(Machine, machine_id)

    if request.method == 'POST':
        try:
            serial_no = request.form['machine_serial_no'].strip()
            duplicate = Machine.query.filter(
                Machine.machine_serial_no == serial_no,
                Machine.machine_id != machine_id,
            ).first()
            if duplicate:
                flash(f'Machine serial number "{serial_no}" already exists.', 'danger')
                return render_template('machines/edit.html', machine=machine,
                                       statuses=MACHINE_STATUSES,
                                       conditions=MACHINE_CONDITIONS,
                                       active_page='machines')

            machine.machine_serial_no = serial_no
            machine.model_name = request.form['model_name'].strip()
            new_status = request.form.get('machine_status', machine.machine_status)
            machine.machine_status = new_status
            machine.machine_condition = request.form.get('machine_condition', machine.machine_condition)
            machine.installation_date = (
                date.fromisoformat(request.form['installation_date'])
                if request.form.get('installation_date') else None
            )
            machine.tds_level = float(request.form['tds_level']) if request.form.get('tds_level') else None
            machine.remarks = request.form.get('remarks', '').strip()

            # If machine is marked Available or Scrapped, unassign it from any customer
            if new_status in ['Available', 'Scrapped'] and machine.assigned_customer_id:
                customer = db.session.get(Customer, machine.assigned_customer_id)
                if customer:
                    customer.machine_id = None
                    customer.machine_serial_no = None

                current_assignment = (
                    MachineAssignmentHistory.query
                    .filter_by(machine_id=machine_id, customer_id=machine.assigned_customer_id)
                    .filter(MachineAssignmentHistory.returned_on.is_(None))
                    .first()
                )
                if current_assignment:
                    current_assignment.returned_on = date.today()
                    current_assignment.remarks = f"Machine marked as {new_status}"

                machine.assigned_customer_id = None
                machine.installation_date = None

            elif machine.assigned_customer_id:
                # Update existing assignment details
                customer = db.session.get(Customer, machine.assigned_customer_id)
                if customer:
                    customer.installation_date = machine.installation_date

                current_assignment = (
                    MachineAssignmentHistory.query
                    .filter_by(machine_id=machine_id, customer_id=machine.assigned_customer_id)
                    .filter(MachineAssignmentHistory.returned_on.is_(None))
                    .first()
                )
                if current_assignment and machine.installation_date:
                    current_assignment.assigned_on = machine.installation_date

            db.session.commit()
            log_activity(current_user.username, 'Edit', 'Machine', machine_id,
                         f'Edited machine {machine.machine_serial_no}', request.remote_addr)
            flash('Machine updated!', 'success')
            return redirect(url_for('machines.view', machine_id=machine_id))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error editing machine {machine_id}: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    return render_template('machines/edit.html', machine=machine,
                           statuses=MACHINE_STATUSES, conditions=MACHINE_CONDITIONS,
                           active_page='machines')


@machine_bp.route('/export/csv')
@login_required
def export_csv():
    """Export machines as CSV."""
    if not current_user.has_permission('machines'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    import pandas as pd
    machines = Machine.query.all()
    rows = [{
        'ID': m.machine_id,
        'Serial No': m.machine_serial_no,
        'Model': m.model_name,
        'Status': m.machine_status,
        'Condition': m.machine_condition,
        'Assigned Customer ID': m.assigned_customer_id,
        'Next Service Date': m.next_service_date,
        'TDS Level': m.tds_level,
    } for m in machines]
    csv = pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig')
    return Response(csv, mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=machines.csv'})


@machine_bp.route('/import/template')
@login_required
def import_template():
    """Download blank CSV import template."""
    if not current_user.has_permission('machines'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    from services.export_service import get_machine_import_template
    return Response(
        get_machine_import_template(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=machine_import_template.csv'},
    )


@machine_bp.route('/import', methods=['POST'])
@login_required
def import_csv():
    """Import machines from CSV with validation."""
    if not current_user.has_permission('machines'):
        flash('Access denied.', 'danger')
        return redirect(url_for('machines.index'))

    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid CSV file.', 'danger')
        return redirect(url_for('machines.add'))

    from services.export_service import import_machines_csv
    result = import_machines_csv(file.stream)
    if result['success']:
        log_activity(current_user.username, 'Import', 'Machine',
                     remarks=f'Imported {result["count"]} machines', ip_address=request.remote_addr)
        flash(f'Successfully imported {result["count"]} machines!', 'success')
        return redirect(url_for('machines.index'))
    else:
        return render_template(
            'machines/add.html',
            statuses=MACHINE_STATUSES,
            conditions=MACHINE_CONDITIONS,
            active_page='machines',
            errors=result['errors']
        )
