"""
routes/employee_routes.py - Employee & Technician management routes.

Supports:
  - Full CRUD for employees (HR records)
  - Daily attendance marking with flexible week-off days
  - Bulk attendance marking for a selected date
  - Salary component records (payments, advances, deductions, bonuses)
  - JSON API endpoint returning active technicians (for maintenance form autocomplete)
"""
from datetime import date, datetime
from calendar import monthrange

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, current_app, jsonify)
from flask_login import login_required, current_user
from sqlalchemy import extract

from extensions import db
from models.employee import (Employee, AttendanceLog, SalaryRecord,
                              EMPLOYEE_TYPES, ATTENDANCE_STATUSES,
                              LEAVE_TYPES, SALARY_COMPONENTS, PAYMENT_MODES)
from utils.helpers import log_activity, get_page_items

employee_bp = Blueprint('employees', __name__, url_prefix='/employees')

# ---------------------------------------------------------------------------
# Permission guard
# ---------------------------------------------------------------------------

def _require_perm():
    """Flash and redirect if user lacks 'employees' permission."""
    if not current_user.has_permission('employees'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    return None


def _require_admin():
    """Flash and redirect if user is not admin."""
    if not current_user.is_admin():
        flash('Admin access required.', 'danger')
        return redirect(url_for('dashboard.index'))
    return None


# ---------------------------------------------------------------------------
# AJAX: Active Technicians list (for maintenance form autocomplete)
# ---------------------------------------------------------------------------

@employee_bp.route('/api/technicians')
@login_required
def api_technicians():
    """Return active Field Technicians as JSON for autocomplete dropdowns."""
    technicians = Employee.query.filter(
        Employee.status == 'Active',
        Employee.emp_type == 'Field Technician',
    ).order_by(Employee.emp_name).all()
    return jsonify([
        {'id': t.emp_id, 'name': t.emp_name, 'phone': t.contact_number}
        for t in technicians
    ])


# ---------------------------------------------------------------------------
# Index — Employee List
# ---------------------------------------------------------------------------

@employee_bp.route('/')
@login_required
def index():
    """Employee list with stats bar, search, and filters."""
    guard = _require_perm()
    if guard:
        return guard

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    type_filter = request.args.get('emp_type', '').strip()
    status_filter = request.args.get('status', '').strip()

    query = Employee.query

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Employee.emp_name.ilike(like),
                Employee.contact_number.ilike(like),
                Employee.emp_code.ilike(like),
                Employee.department.ilike(like),
            )
        )
    if type_filter:
        query = query.filter(Employee.emp_type == type_filter)
    if status_filter:
        query = query.filter(Employee.status == status_filter)

    query = query.order_by(Employee.emp_name)
    pagination = get_page_items(query, page)

    # Stats
    total = Employee.query.count()
    active = Employee.query.filter_by(status='Active').count()
    technicians = Employee.query.filter_by(emp_type='Field Technician', status='Active').count()
    on_leave = Employee.query.filter_by(status='On Leave').count()

    return render_template(
        'employees/index.html',
        employees=pagination.items,
        pagination=pagination,
        search=search,
        type_filter=type_filter,
        status_filter=status_filter,
        emp_types=EMPLOYEE_TYPES,
        statuses=['Active', 'Inactive', 'On Leave', 'Resigned', 'Terminated'],
        total=total,
        active=active,
        technicians=technicians,
        on_leave=on_leave,
        active_page='employees',
    )


# ---------------------------------------------------------------------------
# Add Employee
# ---------------------------------------------------------------------------

@employee_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add a new employee or technician."""
    guard = _require_perm()
    if guard:
        return guard

    if request.method == 'POST':
        try:
            # Auto-generate emp_code if not provided
            emp_code = request.form.get('emp_code', '').strip() or None
            if not emp_code:
                count = Employee.query.count() + 1
                prefix = 'HZ-T' if request.form.get('emp_type') == 'Field Technician' else 'HZ-E'
                emp_code = f'{prefix}{count:03d}'
                # Ensure uniqueness
                while Employee.query.filter_by(emp_code=emp_code).first():
                    count += 1
                    emp_code = f'{prefix}{count:03d}'

            join_raw = request.form.get('join_date', '').strip()
            join_date = date.fromisoformat(join_raw) if join_raw else date.today()

            emp = Employee(
                emp_name=request.form['emp_name'].strip(),
                emp_code=emp_code,
                emp_type=request.form.get('emp_type', 'Field Technician'),
                department=request.form.get('department', '').strip() or None,
                contact_number=request.form.get('contact_number', '').strip(),
                emergency_contact=request.form.get('emergency_contact', '').strip() or None,
                emergency_contact_name=request.form.get('emergency_contact_name', '').strip() or None,
                email=request.form.get('email', '').strip() or None,
                address=request.form.get('address', '').strip() or None,
                city=request.form.get('city', '').strip() or None,
                pin=request.form.get('pin', '').strip() or None,
                join_date=join_date,
                status=request.form.get('status', 'Active'),
                monthly_salary=float(request.form.get('monthly_salary', 0) or 0),
                salary_payment_mode=request.form.get('salary_payment_mode', 'Cash'),
                bank_account_no=request.form.get('bank_account_no', '').strip() or None,
                bank_name=request.form.get('bank_name', '').strip() or None,
                upi_id=request.form.get('upi_id', '').strip() or None,
                aadhar_no=request.form.get('aadhar_no', '').strip() or None,
                pan_no=request.form.get('pan_no', '').strip() or None,
                notes=request.form.get('notes', '').strip() or None,
            )
            db.session.add(emp)
            db.session.commit()
            log_activity(current_user.username, 'Add', 'Employee', emp.emp_id,
                         f'Added employee: {emp.emp_name} ({emp.emp_code})', request.remote_addr)
            flash(f'Employee "{emp.emp_name}" ({emp.emp_code}) added successfully!', 'success')
            return redirect(url_for('employees.view', emp_id=emp.emp_id))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding employee: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    from models.user import User
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    return render_template(
        'employees/add.html',
        emp_types=EMPLOYEE_TYPES,
        payment_modes=PAYMENT_MODES,
        statuses=['Active', 'Inactive', 'On Leave'],
        users=users,
        active_page='employees',
        employee=None,  # Distinguishes add vs edit
    )


# ---------------------------------------------------------------------------
# View Employee Profile
# ---------------------------------------------------------------------------

@employee_bp.route('/<int:emp_id>')
@login_required
def view(emp_id):
    """Employee profile with attendance calendar and salary summary."""
    guard = _require_perm()
    if guard:
        return guard

    emp = db.get_or_404(Employee, emp_id)

    # Current month/year for defaults
    today = date.today()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)

    # Clamp month
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    # Attendance for selected month
    att_logs = AttendanceLog.query.filter(
        AttendanceLog.emp_id == emp_id,
        extract('month', AttendanceLog.att_date) == month,
        extract('year', AttendanceLog.att_date) == year,
    ).order_by(AttendanceLog.att_date).all()

    # Build a dict: {date: log} for quick template lookup
    att_map = {log.att_date: log for log in att_logs}

    # Attendance summary counts
    att_summary = {s: 0 for s in ATTENDANCE_STATUSES}
    for log in att_logs:
        if log.status in att_summary:
            att_summary[log.status] += 1

    # Calendar grid
    first_weekday, days_in_month = monthrange(year, month)
    # first_weekday: 0=Mon, 6=Sun. We want Sunday-first grid (0=Sun).
    # Convert: Sun=0 in our grid. Python gives Mon=0, so Sun=6 from Python.
    # Shift: grid_start = (first_weekday + 1) % 7  (Mon->1, Tue->2, ..., Sun->0)
    grid_offset = (first_weekday + 1) % 7

    # Salary records for selected month
    salary_records = SalaryRecord.query.filter(
        SalaryRecord.emp_id == emp_id,
        extract('month', SalaryRecord.record_date) == month,
        extract('year', SalaryRecord.record_date) == year,
    ).order_by(SalaryRecord.record_date.desc()).all()

    # Net salary calc for month
    net_salary = 0.0
    for r in salary_records:
        if r.component in ('Basic Salary', 'Bonus', 'Incentive', 'Reimbursement'):
            net_salary += r.amount
        else:
            net_salary -= r.amount

    # Recent maintenance records — prefer FK-linked records, fall back to name match
    from models.maintenance import Maintenance
    maintenance_records = Maintenance.query.filter(
        db.or_(
            Maintenance.technician_emp_id == emp_id,
            Maintenance.technician_name.ilike(f'%{emp.emp_name}%'),
        )
    ).order_by(Maintenance.service_date.desc()).limit(10).all()

    # Installations done by this employee
    from models.customer import Customer
    installation_records = Customer.query.filter_by(
        installed_by_emp_id=emp_id
    ).order_by(Customer.installation_date.desc()).limit(10).all()

    return render_template(
        'employees/view.html',
        emp=emp,
        att_map=att_map,
        att_summary=att_summary,
        att_statuses=ATTENDANCE_STATUSES,
        grid_offset=grid_offset,
        days_in_month=days_in_month,
        month=month,
        year=year,
        today=today,
        salary_records=salary_records,
        net_salary=net_salary,
        salary_components=SALARY_COMPONENTS,
        payment_modes=PAYMENT_MODES,
        maintenance_records=maintenance_records,
        installation_records=installation_records,
        active_page='employees',
    )


# ---------------------------------------------------------------------------
# Edit Employee
# ---------------------------------------------------------------------------

@employee_bp.route('/<int:emp_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(emp_id):
    """Edit employee details."""
    guard = _require_perm()
    if guard:
        return guard

    emp = db.get_or_404(Employee, emp_id)

    if request.method == 'POST':
        try:
            emp.emp_name = request.form.get('emp_name', emp.emp_name).strip()
            emp.emp_code = request.form.get('emp_code', emp.emp_code).strip() or emp.emp_code
            emp.emp_type = request.form.get('emp_type', emp.emp_type)
            emp.department = request.form.get('department', '').strip() or None
            emp.contact_number = request.form.get('contact_number', emp.contact_number).strip()
            emp.emergency_contact = request.form.get('emergency_contact', '').strip() or None
            emp.emergency_contact_name = request.form.get('emergency_contact_name', '').strip() or None
            emp.email = request.form.get('email', '').strip() or None
            emp.address = request.form.get('address', '').strip() or None
            emp.city = request.form.get('city', '').strip() or None
            emp.pin = request.form.get('pin', '').strip() or None
            emp.status = request.form.get('status', emp.status)
            emp.monthly_salary = float(request.form.get('monthly_salary', emp.monthly_salary) or 0)
            emp.salary_payment_mode = request.form.get('salary_payment_mode', emp.salary_payment_mode)
            emp.bank_account_no = request.form.get('bank_account_no', '').strip() or None
            emp.bank_name = request.form.get('bank_name', '').strip() or None
            emp.upi_id = request.form.get('upi_id', '').strip() or None
            emp.aadhar_no = request.form.get('aadhar_no', '').strip() or None
            emp.pan_no = request.form.get('pan_no', '').strip() or None
            emp.notes = request.form.get('notes', '').strip() or None

            join_raw = request.form.get('join_date', '').strip()
            if join_raw:
                emp.join_date = date.fromisoformat(join_raw)

            exit_raw = request.form.get('exit_date', '').strip()
            emp.exit_date = date.fromisoformat(exit_raw) if exit_raw else None

            db.session.commit()
            log_activity(current_user.username, 'Edit', 'Employee', emp.emp_id,
                         f'Updated employee: {emp.emp_name}', request.remote_addr)
            flash('Employee updated successfully!', 'success')
            return redirect(url_for('employees.view', emp_id=emp.emp_id))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error editing employee {emp_id}: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    from models.user import User
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    return render_template(
        'employees/add.html',
        emp_types=EMPLOYEE_TYPES,
        payment_modes=PAYMENT_MODES,
        statuses=['Active', 'Inactive', 'On Leave', 'Resigned', 'Terminated'],
        users=users,
        active_page='employees',
        employee=emp,   # Non-None = edit mode
    )


# ---------------------------------------------------------------------------
# Toggle Employee Status (Activate / Deactivate)
# ---------------------------------------------------------------------------

@employee_bp.route('/<int:emp_id>/toggle', methods=['POST'])
@login_required
def toggle(emp_id):
    """Toggle Active / Inactive status."""
    guard = _require_perm()
    if guard:
        return guard

    emp = db.get_or_404(Employee, emp_id)
    new_status = 'Inactive' if emp.status == 'Active' else 'Active'
    emp.status = new_status
    db.session.commit()
    log_activity(current_user.username, 'Toggle', 'Employee', emp.emp_id,
                 f'Status changed to {new_status}', request.remote_addr)
    flash(f'"{emp.emp_name}" marked as {new_status}.', 'success')
    return redirect(url_for('employees.view', emp_id=emp.emp_id))


# ---------------------------------------------------------------------------
# Attendance — Mark single employee for today
# ---------------------------------------------------------------------------

@employee_bp.route('/<int:emp_id>/attendance', methods=['POST'])
@login_required
def mark_attendance(emp_id):
    """Mark or update attendance for a single employee on a given date."""
    guard = _require_perm()
    if guard:
        return guard

    emp = db.get_or_404(Employee, emp_id)
    att_date_raw = request.form.get('att_date', '').strip()
    att_status = request.form.get('att_status', 'Present').strip()
    leave_type = request.form.get('leave_type', '').strip() or None
    check_in = request.form.get('check_in', '').strip() or None
    check_out = request.form.get('check_out', '').strip() or None
    notes = request.form.get('notes', '').strip() or None

    try:
        att_date = date.fromisoformat(att_date_raw) if att_date_raw else date.today()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('employees.view', emp_id=emp_id))

    # Upsert: update existing or create new
    existing = AttendanceLog.query.filter_by(emp_id=emp_id, att_date=att_date).first()
    if existing:
        existing.status = att_status
        existing.leave_type = leave_type
        existing.check_in = check_in
        existing.check_out = check_out
        existing.notes = notes
        existing.marked_by = current_user.username
    else:
        log = AttendanceLog(
            emp_id=emp_id,
            att_date=att_date,
            status=att_status,
            leave_type=leave_type,
            check_in=check_in,
            check_out=check_out,
            notes=notes,
            marked_by=current_user.username,
        )
        db.session.add(log)

    db.session.commit()

    # Redirect back to the same month view
    return redirect(url_for('employees.view', emp_id=emp_id,
                            month=att_date.month, year=att_date.year))


# ---------------------------------------------------------------------------
# Attendance — Bulk marking for a date (all employees at once)
# ---------------------------------------------------------------------------

@employee_bp.route('/attendance/bulk', methods=['GET', 'POST'])
@login_required
def bulk_attendance():
    """
    Bulk attendance marking for a selected date.

    - Admin selects any date (any day can be a Week Off for any employee).
    - The form shows all active employees with a status dropdown per row.
    - There is NO fixed week-off day — each row can be independently set
      to 'Week Off', 'Present', 'Absent', etc.
    """
    guard = _require_perm()
    if guard:
        return guard

    today = date.today()
    att_date_raw = request.args.get('att_date', today.isoformat())
    try:
        att_date = date.fromisoformat(att_date_raw)
    except ValueError:
        att_date = today

    active_employees = Employee.query.filter(
        Employee.status.in_(['Active', 'On Leave'])
    ).order_by(Employee.emp_type, Employee.emp_name).all()

    # Load existing attendance for this date
    existing_logs = AttendanceLog.query.filter_by(att_date=att_date).all()
    existing_map = {log.emp_id: log for log in existing_logs}

    if request.method == 'POST':
        att_date_raw_post = request.form.get('att_date', today.isoformat())
        try:
            att_date = date.fromisoformat(att_date_raw_post)
        except ValueError:
            att_date = today

        saved = 0
        try:
            for emp in active_employees:
                att_status = request.form.get(f'status_{emp.emp_id}', '').strip()
                if not att_status:
                    continue  # Skip if not submitted (optional)

                leave_type = request.form.get(f'leave_type_{emp.emp_id}', '').strip() or None
                notes = request.form.get(f'notes_{emp.emp_id}', '').strip() or None

                existing = existing_map.get(emp.emp_id)
                if existing:
                    existing.status = att_status
                    existing.leave_type = leave_type
                    existing.notes = notes
                    existing.marked_by = current_user.username
                else:
                    log = AttendanceLog(
                        emp_id=emp.emp_id,
                        att_date=att_date,
                        status=att_status,
                        leave_type=leave_type,
                        notes=notes,
                        marked_by=current_user.username,
                    )
                    db.session.add(log)
                saved += 1

            db.session.commit()
            log_activity(current_user.username, 'Bulk Attendance', 'Employee',
                         remarks=f'Marked attendance for {saved} employees on {att_date}',
                         ip_address=request.remote_addr)
            flash(f'Attendance saved for {saved} employees on {att_date.strftime("%d %b %Y")}.', 'success')
            return redirect(url_for('employees.bulk_attendance', att_date=att_date.isoformat()))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Bulk attendance error: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    return render_template(
        'employees/attendance.html',
        employees=active_employees,
        existing_map=existing_map,
        att_date=att_date,
        att_statuses=ATTENDANCE_STATUSES,
        leave_types=LEAVE_TYPES,
        active_page='employees',
    )


# ---------------------------------------------------------------------------
# Salary — Add a salary record
# ---------------------------------------------------------------------------

@employee_bp.route('/<int:emp_id>/salary/add', methods=['POST'])
@login_required
def add_salary(emp_id):
    """Add a salary component record (payment, advance, bonus, deduction)."""
    guard = _require_perm()
    if guard:
        return guard

    emp = db.get_or_404(Employee, emp_id)

    try:
        record_date_raw = request.form.get('record_date', '').strip()
        record_date = date.fromisoformat(record_date_raw) if record_date_raw else date.today()
        component = request.form.get('component', 'Basic Salary').strip()
        amount = float(request.form.get('amount', 0) or 0)
        if amount <= 0:
            flash('Amount must be greater than zero.', 'warning')
            return redirect(url_for('employees.view', emp_id=emp_id))

        record = SalaryRecord(
            emp_id=emp_id,
            record_date=record_date,
            component=component,
            amount=amount,
            payment_mode=request.form.get('payment_mode', 'Cash'),
            reference_no=request.form.get('reference_no', '').strip() or None,
            remarks=request.form.get('remarks', '').strip() or None,
            paid_by=current_user.username,
        )
        db.session.add(record)
        db.session.commit()
        log_activity(current_user.username, 'Add', 'SalaryRecord', record.record_id,
                     f'{component} ₹{amount} for {emp.emp_name}', request.remote_addr)
        flash(f'{component} of ₹{amount:,.0f} recorded for {emp.emp_name}.', 'success')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f'Error adding salary record: {exc}', exc_info=True)
        flash(f'Error: {exc}', 'danger')

    month = request.form.get('redirect_month', date.today().month)
    year = request.form.get('redirect_year', date.today().year)
    return redirect(url_for('employees.view', emp_id=emp_id, month=month, year=year))


# ---------------------------------------------------------------------------
# Salary — Delete a salary record
# ---------------------------------------------------------------------------

@employee_bp.route('/salary/<int:record_id>/delete', methods=['POST'])
@login_required
def delete_salary(record_id):
    """Delete a salary record (admin only)."""
    guard = _require_admin()
    if guard:
        return guard

    record = db.get_or_404(SalaryRecord, record_id)
    emp_id = record.emp_id
    month = record.record_date.month
    year = record.record_date.year
    try:
        db.session.delete(record)
        db.session.commit()
        log_activity(current_user.username, 'Delete', 'SalaryRecord', record_id,
                     f'Deleted {record.component} ₹{record.amount}', request.remote_addr)
        flash('Salary record deleted.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Error: {exc}', 'danger')

    return redirect(url_for('employees.view', emp_id=emp_id, month=month, year=year))
