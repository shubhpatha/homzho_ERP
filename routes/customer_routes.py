"""
routes/customer_routes.py - Full customer CRUD with search, filter, CSV import/export.
"""
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import urllib.parse
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, Response, current_app)
from flask_login import login_required, current_user
from extensions import db
from models.customer import Customer
from models.machine import Machine, MachineAssignmentHistory
from models.plan import Plan
from models.payment import Payment
from models.maintenance import Maintenance
from models.upload import Upload
from models.employee import Employee
from services.export_service import (
    export_customers_csv, get_customer_import_template, import_customers_csv
)
from services.accounting_service import sync_installation_cost_to_ledger
from utils.referrals import generate_referral_token
from utils.helpers import log_activity, get_page_items

customer_bp = Blueprint('customers', __name__, url_prefix='/customers')


# ---------------------------------------------------------------------------
# List / Search / Filter
# ---------------------------------------------------------------------------

@customer_bp.route('/')
@login_required
def index():
    """Customer listing with search and filters."""
    if not current_user.has_permission('customers'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    city_filter = request.args.get('city', '').strip()
    area_filter = request.args.get('area', '').strip()
    status_filter = request.args.get('status', '').strip()
    plan_filter = request.args.get('plan', '').strip()

    query = Customer.query

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Customer.cust_name.ilike(like),
                Customer.contact_number.ilike(like),
                Customer.email_id.ilike(like),
                Customer.machine_serial_no.ilike(like),
            )
        )
    if city_filter:
        query = query.filter(Customer.city.ilike(f'%{city_filter}%'))
    if area_filter:
        query = query.filter(Customer.area.ilike(f'%{area_filter}%'))
    if status_filter:
        query = query.filter(Customer.customer_status == status_filter)
    if plan_filter:
        query = query.filter(Customer.plan_name.ilike(f'%{plan_filter}%'))

    query = query.order_by(Customer.created_at.desc())
    pagination = get_page_items(query, page)

    # Distinct cities and areas for filter dropdowns
    cities = [r[0] for r in db.session.query(Customer.city).distinct().all() if r[0]]
    areas  = [r[0] for r in db.session.query(Customer.area).distinct().all() if r[0]]

    return render_template(
        'customers/index.html',
        customers=pagination.items,
        pagination=pagination,
        search=search,
        city_filter=city_filter,
        area_filter=area_filter,
        status_filter=status_filter,
        plan_filter=plan_filter,
        cities=cities,
        areas=areas,
        active_page='customers',
    )


# ---------------------------------------------------------------------------
# Add Customer
# ---------------------------------------------------------------------------

@customer_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add a new customer."""
    if not current_user.has_permission('customers'):
        flash('Access denied.', 'danger')
        return redirect(url_for('customers.index'))

    machines = Machine.query.filter_by(machine_status='Available').all()
    plans = Plan.query.filter_by(is_active=True).order_by(Plan.validity_in_days.asc()).all()
    all_customers = Customer.query.filter_by(customer_status='Active').order_by(Customer.cust_name).all()
    technicians = Employee.query.filter(
        Employee.status == 'Active',
        Employee.emp_type.in_(['Field Technician', 'Manager', 'Other'])
    ).order_by(Employee.emp_name).all()

    # Pre-populate form from URL query params (e.g., when converting a Lead)
    form_data = {k: v for k, v in request.args.items()} if request.method == 'GET' else {}
    errors = {}

    if request.method == 'POST':
        form_data = request.form.to_dict()

        # ── Server-side mandatory field validation ──────────────────────────
        if not form_data.get('cust_name', '').strip():
            errors['cust_name'] = 'Full name is required.'

        contact = form_data.get('contact_number', '').strip()
        if not contact:
            errors['contact_number'] = 'Contact number is required.'
        elif not contact.isdigit() or len(contact) < 10 or len(contact) > 15:
            errors['contact_number'] = 'Enter a valid 10–15 digit mobile number.'
        else:
            duplicate = Customer.query.filter_by(contact_number=contact).first()
            if duplicate:
                errors['contact_number'] = f'Number already registered to {duplicate.cust_name}.'

        if not form_data.get('plan_id', '').strip():
            errors['plan_id'] = 'Please select a rental plan.'

        if not form_data.get('plan_start_date', '').strip():
            errors['plan_start_date'] = 'Plan start date is required.'

        pin = form_data.get('pin', '').strip()
        if pin and (not pin.isdigit() or len(pin) != 6):
            errors['pin'] = 'PIN must be exactly 6 digits.'

        # ── Re-render form with errors if validation failed ─────────────────
        if errors:
            return render_template(
                'customers/add.html',
                machines=machines, plans=plans, all_customers=all_customers,
                technicians=technicians,
                form_data=form_data, errors=errors,
                active_page='customers',
            )

        # ── Validation passed — save to database ────────────────────────────
        try:
            plan_start = date.fromisoformat(request.form['plan_start_date'])
            plan = db.get_or_404(Plan, int(request.form['plan_id']))
            plan_end = plan_start + timedelta(days=plan.validity_in_days)

            customer = Customer(
                cust_name=request.form['cust_name'].strip(),
                contact_number=contact,
                email_id=request.form.get('email_id', '').strip() or None,
                plan_name=plan.plan_name,
                plan_duration_months=plan.duration_months,
                plan_start_date=plan_start,
                plan_end_date=plan_end,
                payment_freq=plan.payment_frequency,
                monthly_rent=plan.cost,
                deposit=float(request.form.get('deposit', 0) or 0),
                customer_status='Active',
                address=request.form.get('address', '').strip(),
                area=request.form.get('area', '').strip(),
                city=request.form.get('city', '').strip(),
                pin=pin,
                notes=request.form.get('notes', '').strip(),
                installed_by=request.form.get('installed_by', '').strip(),
                installation_cost=float(request.form.get('installation_cost', 0) or 0),
                next_billing_date=plan_end,
                referred_by_id=int(request.form['referred_by_id']) if request.form.get('referred_by_id') else None
            )

            # Link installer to employee if selected from dropdown
            installer_emp_id_raw = request.form.get('installed_by_emp_id', '').strip()
            if installer_emp_id_raw and installer_emp_id_raw.isdigit():
                emp = db.session.get(Employee, int(installer_emp_id_raw))
                if emp:
                    customer.installed_by_emp_id = emp.emp_id
                    customer.installed_by = emp.emp_name  # keep text field in sync

            machine_id = request.form.get('machine_id')
            machine = None
            # Months until next service (from dropdown; default 3)
            next_svc_months = int(request.form.get('next_service_months') or 3)
            if machine_id:
                machine = db.session.get(Machine, int(machine_id))
                if machine and machine.machine_status == 'Available':
                    customer.machine_id = machine.machine_id
                    customer.machine_serial_no = machine.machine_serial_no
                    customer.installation_date = (
                        date.fromisoformat(request.form['installation_date'])
                        if request.form.get('installation_date') else date.today()
                    )
                    # next_service_date lives on Machine only (Customer reads it via @property)

            db.session.add(customer)
            db.session.flush()

            if customer.machine_id and machine:
                machine.machine_status = 'Installed'
                machine.assigned_customer_id = customer.cust_id
                machine.installation_date = customer.installation_date
                machine.next_service_date = customer.installation_date + relativedelta(months=next_svc_months)
                db.session.add(MachineAssignmentHistory(
                    machine_id=machine.machine_id,
                    customer_id=customer.cust_id,
                    assigned_on=customer.installation_date or date.today(),
                    remarks='Initial assignment on customer creation',
                ))

            db.session.commit()
            # Sync installation cost to the accounting ledger
            sync_installation_cost_to_ledger(customer, created_by=current_user.username)
            db.session.commit()
            log_activity(
                user_name=current_user.username,
                action_type='Add', module_name='Customer',
                record_id=customer.cust_id,
                remarks=f'Added customer: {customer.cust_name}',
                ip_address=request.remote_addr,
            )

            # Auto-mark any matching lead as Converted
            from models.lead import Lead as LeadModel

            lead_to_convert = None

            # Primary: use from_lead ID if present (fastest, most reliable)
            from_lead_id = request.form.get('from_lead')
            if from_lead_id and from_lead_id.isdigit():
                lead_to_convert = db.session.get(LeadModel, int(from_lead_id))

            # Fallback: search by contact number with digit-only normalization
            # This covers the case where someone manually adds a customer whose
            # contact was already registered as a lead (no from_lead in form)
            if not lead_to_convert:
                # Normalize to digits only for a reliable comparison
                digits_only = ''.join(filter(str.isdigit, contact))
                # Fetch all unconverted leads and compare digit-normalized numbers
                unconverted_leads = LeadModel.query.filter(
                    LeadModel.status != 'Converted'
                ).all()
                for l in unconverted_leads:
                    if ''.join(filter(str.isdigit, l.contact_number)) == digits_only:
                        lead_to_convert = l
                        break

            if lead_to_convert and lead_to_convert.status != 'Converted':
                lead_to_convert.status = 'Converted'
                db.session.commit()

            wa_link = None
            if customer.referred_by_id:
                referrer = db.session.get(Customer, customer.referred_by_id)
                if referrer and referrer.contact_number:
                    from services.whatsapp_service import get_referral_thank_you_link
                    wa_link = get_referral_thank_you_link(referrer.cust_name, referrer.contact_number, customer.cust_name)

            if wa_link:
                flash(f'Customer "{customer.cust_name}" added successfully! <a href="{wa_link}" target="_blank" class="alert-link ms-2"><i class="bi bi-whatsapp"></i> Send Referral Thank You</a>', 'success')
            else:
                flash(f'Customer "{customer.cust_name}" added successfully!', 'success')
            return redirect(url_for('customers.view', cust_id=customer.cust_id))

        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding customer: {exc}', exc_info=True)
            flash(f'Error adding customer: {exc}', 'danger')

    return render_template('customers/add.html', machines=machines, plans=plans,
                           all_customers=all_customers, technicians=technicians,
                           form_data=form_data, errors=errors, active_page='customers')


# ---------------------------------------------------------------------------
# View Customer Profile
# ---------------------------------------------------------------------------

@customer_bp.route('/<int:cust_id>')
@login_required
def view(cust_id):
    """Detailed customer profile page."""
    if not current_user.has_permission('customers'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    customer = db.get_or_404(Customer, cust_id)
    payments = Payment.query.filter_by(customer_id=cust_id).order_by(Payment.payment_date.desc()).all()
    # Query by customer_id OR by the machine currently assigned to this customer
    # (customer_id is nullable — records added from the machine/maintenance module
    #  may only have machine_id set, so we must include both paths)
    _maint_filter = [Maintenance.customer_id == cust_id]
    if customer.machine_id:
        _maint_filter.append(Maintenance.machine_id == customer.machine_id)
    maintenance_records = (
        Maintenance.query
        .filter(db.or_(*_maint_filter))
        .order_by(Maintenance.service_date.desc())
        .distinct()
        .all()
    )
    uploads = Upload.query.filter_by(customer_id=cust_id).order_by(Upload.uploaded_at.desc()).all()
    assignment_history = MachineAssignmentHistory.query.filter_by(customer_id=cust_id).order_by(MachineAssignmentHistory.assigned_on.desc()).all()
    referral_token = generate_referral_token(customer.cust_id)
    referral_link = url_for('leads.referral_capture', token=referral_token, _external=True)
    referral_share_text = (
        f"Hi, I use Homzho water purifier service. "
        f"You can request a callback here: {referral_link}"
    )
    referral_whatsapp_link = f"https://wa.me/?text={urllib.parse.quote(referral_share_text)}"

    return render_template(
        'customers/view.html',
        customer=customer,
        payments=payments,
        maintenance_records=maintenance_records,
        uploads=uploads,
        assignment_history=assignment_history,
        referral_link=referral_link,
        referral_whatsapp_link=referral_whatsapp_link,
        active_page='customers',
        today=date.today(),
    )


# ---------------------------------------------------------------------------
# Edit Customer
# ---------------------------------------------------------------------------

@customer_bp.route('/<int:cust_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(cust_id):
    """Edit customer details."""
    if not current_user.has_permission('customers'):
        flash('Access denied.', 'danger')
        return redirect(url_for('customers.index'))

    customer = db.get_or_404(Customer, cust_id)
    machines = Machine.query.filter(
        db.or_(Machine.machine_status == 'Available', Machine.machine_id == customer.machine_id)
    ).all()
    plans = Plan.query.filter(
        db.or_(Plan.is_active.is_(True), Plan.plan_name == customer.plan_name)
    ).order_by(Plan.validity_in_days.asc()).all()
    selected_plan = Plan.query.filter_by(plan_name=customer.plan_name).first()
    if not selected_plan:
        selected_plan = Plan.query.filter_by(cost=customer.monthly_rent, is_active=True).first()
    technicians = Employee.query.filter(
        Employee.status == 'Active',
        Employee.emp_type.in_(['Field Technician', 'Manager', 'Other'])
    ).order_by(Employee.emp_name).all()

    if request.method == 'POST':
        try:
            plan = db.get_or_404(Plan, int(request.form['plan_id']))
            new_start_date = date.fromisoformat(request.form['plan_start_date'])
            
            # Check if plan or start date changed to auto-update next billing date
            plan_changed = (customer.plan_name != plan.plan_name)
            start_date_changed = (customer.plan_start_date != new_start_date)

            customer.cust_name = request.form['cust_name'].strip()
            customer.contact_number = request.form['contact_number'].strip()
            customer.email_id = request.form.get('email_id', '').strip() or None
            customer.plan_name = plan.plan_name
            customer.plan_duration_months = plan.duration_months
            customer.plan_start_date = new_start_date
            customer.plan_end_date = customer.plan_start_date + timedelta(days=plan.validity_in_days)
            customer.payment_freq = plan.payment_frequency
            customer.monthly_rent = plan.cost
            customer.deposit = float(request.form.get('deposit', 0) or 0)
            customer.customer_status = request.form.get('customer_status', 'Active')
            customer.address = request.form.get('address', '').strip()
            customer.area = request.form.get('area', '').strip()
            customer.city = request.form.get('city', '').strip()
            customer.pin = request.form.get('pin', '').strip()
            customer.notes = request.form.get('notes', '').strip()
            installation_date_raw = request.form.get('installation_date', '').strip()
            customer.installation_date = (
                date.fromisoformat(installation_date_raw)
                if installation_date_raw else None
            )
            customer.installed_by = request.form.get('installed_by', '').strip()
            customer.installation_cost = float(request.form.get('installation_cost', 0) or 0)

            # Link installer to employee if selected from dropdown
            installer_emp_id_raw = request.form.get('installed_by_emp_id', '').strip()
            if installer_emp_id_raw and installer_emp_id_raw.isdigit():
                emp = db.session.get(Employee, int(installer_emp_id_raw))
                if emp:
                    customer.installed_by_emp_id = emp.emp_id
                    customer.installed_by = emp.emp_name
            elif not installer_emp_id_raw:
                customer.installed_by_emp_id = None

            if plan_changed or start_date_changed:
                customer.next_billing_date = customer.plan_end_date
            elif request.form.get('next_billing_date'):
                customer.next_billing_date = date.fromisoformat(request.form['next_billing_date'])

            # Handle machine reassignment
            new_machine_id_raw = request.form.get('machine_id', '').strip()
            new_machine_id = int(new_machine_id_raw) if new_machine_id_raw else None
            old_machine_id = customer.machine_id
            if new_machine_id and customer.installation_date is None:
                selected_machine = db.session.get(Machine, new_machine_id)
                customer.installation_date = (
                    selected_machine.installation_date
                    if selected_machine and selected_machine.installation_date
                    else date.today()
                )
            assignment_date = customer.installation_date or date.today()

            if new_machine_id != old_machine_id:
                # Unassign old machine
                if old_machine_id:
                    old_machine = db.session.get(Machine, old_machine_id)
                    if old_machine and old_machine.assigned_customer_id == cust_id:
                        old_machine.machine_status = 'Available'
                        old_machine.assigned_customer_id = None
                        old_machine.installation_date = None
                    # Close old assignment history
                    old_hist = (MachineAssignmentHistory.query
                                .filter_by(machine_id=old_machine_id, customer_id=cust_id)
                                .filter(MachineAssignmentHistory.returned_on.is_(None))
                                .first())
                    if old_hist:
                        old_hist.returned_on = date.today()

                if new_machine_id:
                    # Assign new machine
                    new_machine = db.session.get(Machine, new_machine_id)
                    if not new_machine:
                        raise ValueError('Selected machine was not found.')

                    # Clear it from previous owner if necessary
                    if new_machine.assigned_customer_id and new_machine.assigned_customer_id != cust_id:
                        prev_customer_id = new_machine.assigned_customer_id
                        prev_cust = db.session.get(Customer, prev_customer_id)
                        if prev_cust and prev_cust.machine_id == new_machine_id:
                            prev_cust.machine_id = None
                            prev_cust.machine_serial_no = None

                        prev_hist = (MachineAssignmentHistory.query
                                     .filter_by(machine_id=new_machine_id, customer_id=prev_customer_id)
                                     .filter(MachineAssignmentHistory.returned_on.is_(None))
                                     .first())
                        if prev_hist:
                            prev_hist.returned_on = date.today()

                    customer.machine_id = new_machine_id
                    customer.machine_serial_no = new_machine.machine_serial_no
                    new_machine.machine_status = 'Installed'
                    new_machine.assigned_customer_id = cust_id
                    new_machine.installation_date = assignment_date
                    # next_service_date is intentionally left as-is (set by Maintenance module)
                    hist = MachineAssignmentHistory(
                        machine_id=new_machine_id,
                        customer_id=cust_id,
                        assigned_on=assignment_date,
                        remarks='Reassigned during customer edit',
                    )
                    db.session.add(hist)
                else:
                    customer.machine_id = None
                    customer.machine_serial_no = None
                    customer.installation_date = None
                    customer.next_service_date = None
            elif customer.machine_id:
                # Machine is UNCHANGED — never touch next_service_date here.
                # It is exclusively managed by the Maintenance module.
                machine = db.session.get(Machine, customer.machine_id)
                if machine and machine.assigned_customer_id in (None, cust_id):
                    machine.machine_status = 'Installed'
                    machine.assigned_customer_id = cust_id
                    machine.installation_date = assignment_date

            db.session.commit()
            # Sync (upsert or remove) installation cost in the accounting ledger
            sync_installation_cost_to_ledger(customer, created_by=current_user.username)
            db.session.commit()
            log_activity(current_user.username, 'Edit', 'Customer', cust_id,
                         f'Edited customer: {customer.cust_name}', request.remote_addr)
            flash('Customer updated successfully!', 'success')
            return redirect(url_for('customers.view', cust_id=cust_id))

        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error editing customer {cust_id}: {exc}', exc_info=True)
            flash(f'Error updating customer: {exc}', 'danger')

    return render_template('customers/edit.html', customer=customer, machines=machines,
                           plans=plans, technicians=technicians,
                           selected_plan_id=selected_plan.plan_id if selected_plan else None,
                           active_page='customers')


# ---------------------------------------------------------------------------
# Delete Customer
# ---------------------------------------------------------------------------

@customer_bp.route('/<int:cust_id>/delete', methods=['POST'])
@login_required
def delete(cust_id):
    """Mark customer as Cancelled (soft delete)."""
    if not current_user.is_admin():
        flash('Only admins can delete customers.', 'danger')
        return redirect(url_for('customers.index'))

    customer = db.get_or_404(Customer, cust_id)
    try:
        customer.customer_status = 'Cancelled'
        customer.contract_end_date = date.today()
        customer.contract_end_reason = request.form.get('reason', 'Deleted by admin')

        # Release machine
        if customer.machine_id:
            machine = db.session.get(Machine, customer.machine_id)
            if machine:
                machine.machine_status = 'Available'
                machine.assigned_customer_id = None
            customer.machine_id = None
            customer.machine_serial_no = None

        db.session.commit()
        log_activity(current_user.username, 'Delete', 'Customer', cust_id,
                     f'Cancelled customer: {customer.cust_name}', request.remote_addr)
        flash(f'Customer "{customer.cust_name}" has been cancelled.', 'warning')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f'Error deleting customer {cust_id}: {exc}', exc_info=True)
        flash(f'Error: {exc}', 'danger')

    return redirect(url_for('customers.index'))


# ---------------------------------------------------------------------------
# CSV Export / Import
# ---------------------------------------------------------------------------

@customer_bp.route('/export/csv')
@login_required
def export_csv():
    """Export all customers as CSV."""
    if not current_user.has_permission('customers'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    csv_bytes = export_customers_csv()
    return Response(
        csv_bytes,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=customers.csv'},
    )


@customer_bp.route('/import/template')
@login_required
def import_template():
    """Download blank CSV import template."""
    if not current_user.has_permission('customers'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    return Response(
        get_customer_import_template(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=customer_import_template.csv'},
    )


@customer_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_csv():
    """Import customers from CSV with validation."""
    if not current_user.is_admin():
        flash('Only admins can import customers.', 'danger')
        return redirect(url_for('customers.index'))

    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or not file.filename.endswith('.csv'):
            flash('Please upload a valid CSV file.', 'danger')
            return redirect(request.url)

        result = import_customers_csv(file.stream)
        if result['success']:
            log_activity(current_user.username, 'Import', 'Customer',
                         remarks=f'Imported {result["count"]} customers', ip_address=request.remote_addr)
            flash(f'Successfully imported {result["count"]} customers!', 'success')
            return redirect(url_for('customers.index'))
        else:
            return render_template('customers/import.html',
                                   errors=result['errors'], active_page='customers')

    return render_template('customers/import.html', errors=None, active_page='customers')
