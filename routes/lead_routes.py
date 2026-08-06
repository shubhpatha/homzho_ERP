"""
routes/lead_routes.py - Lead Management routes.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from extensions import db
from models.lead import Lead
from models.customer import Customer
from models.plan import Plan
from services.meta_service import send_conversion_event
from services.whatsapp_service import get_lead_followup_link
from utils.helpers import clean_phone, log_activity, get_page_items
from utils.referrals import load_referral_customer_id

lead_bp = Blueprint('leads', __name__, url_prefix='/leads')

LEAD_SOURCES = ['Organic', 'Meta Ads', 'Google Ads', 'Referral', 'Other']
LEAD_SCORES = ['Hot', 'Warm', 'Cold']
LEAD_STATUSES = ['New', 'Contacted', 'Qualified', 'Lost', 'Converted']


@lead_bp.route('/ref/<token>', methods=['GET', 'POST'])
def referral_capture(token):
    """Public referral lead form opened from an existing customer's share link."""
    referrer_id = load_referral_customer_id(token)
    referrer = db.session.get(Customer, referrer_id) if referrer_id else None
    if not referrer or referrer.customer_status != 'Active':
        return render_template('leads/referral_capture.html', invalid_link=True), 404

    form_data = {
        'name': request.form.get('name', '').strip(),
        'contact_number': request.form.get('contact_number', '').strip(),
        'email_id': request.form.get('email_id', '').strip(),
    }
    errors = {}

    if request.method == 'POST':
        contact = clean_phone(form_data['contact_number'])
        if not contact:
            errors['contact_number'] = 'Phone number is required.'
        elif len(contact) < 10 or len(contact) > 15:
            errors['contact_number'] = 'Enter a valid 10-15 digit phone number.'

        existing_customer = Customer.query.filter_by(contact_number=contact).first() if contact else None
        existing_lead = Lead.query.filter_by(contact_number=contact).first() if contact else None

        if not errors and existing_customer:
            return render_template(
                'leads/referral_capture.html',
                referrer=referrer,
                already_exists=True,
            )

        if not errors and existing_lead:
            if not existing_lead.referred_by_id:
                existing_lead.referred_by_id = referrer.cust_id
                existing_lead.source = 'Referral'
                existing_lead.notes = (existing_lead.notes or '').strip()
                referral_note = f'Referral link submitted by {referrer.cust_name}.'
                if referral_note not in existing_lead.notes:
                    existing_lead.notes = f"{existing_lead.notes}\n{referral_note}".strip()
                db.session.commit()
            return render_template(
                'leads/referral_capture.html',
                referrer=referrer,
                submitted=True,
            )

        if not errors:
            name = form_data['name'] or f'Referral Lead {contact[-4:]}'
            lead = Lead(
                name=name,
                contact_number=contact,
                email_id=form_data['email_id'] or None,
                source='Referral',
                score='Warm',
                status='New',
                referred_by_id=referrer.cust_id,
                notes=f'Referral link submitted by {referrer.cust_name}.',
            )
            try:
                db.session.add(lead)
                db.session.commit()
                log_activity(
                    'Public Referral',
                    'Add',
                    'Lead',
                    lead.lead_id,
                    f'Referral lead from customer #{referrer.cust_id}',
                    request.remote_addr,
                )
                send_conversion_event(lead, event_name="Lead")
                return render_template(
                    'leads/referral_capture.html',
                    referrer=referrer,
                    submitted=True,
                )
            except Exception as exc:
                db.session.rollback()
                current_app.logger.error(f'Error adding referral lead: {exc}', exc_info=True)
                errors['form'] = 'We could not save your request right now. Please try again.'

    return render_template(
        'leads/referral_capture.html',
        referrer=referrer,
        form_data=form_data,
        errors=errors,
    )

@lead_bp.route('/')
@login_required
def index():
    """List all leads."""
    from datetime import date
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    score_filter = request.args.get('score', '').strip()
    contact_date_filter = request.args.get('contact_date', '').strip()  # YYYY-MM-DD
    sort = request.args.get('sort', '').strip()          # 'added_on' | 'next_contact'
    sort_dir = request.args.get('sort_dir', 'asc').strip()  # 'asc' | 'desc'

    query = Lead.query

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Lead.name.ilike(like),
                Lead.contact_number.ilike(like)
            )
        )
    if status_filter:
        query = query.filter(Lead.status == status_filter)
    if score_filter:
        query = query.filter(Lead.score == score_filter)
    if contact_date_filter:
        try:
            filter_date = date.fromisoformat(contact_date_filter)
            query = query.filter(Lead.next_contact_date == filter_date)
        except ValueError:
            pass  # ignore bad date input

    # Sort by user-selected column, or fall back to default
    if sort == 'added_on':
        col = Lead.created_at
        query = query.order_by(col.desc() if sort_dir == 'desc' else col.asc())
    elif sort == 'next_contact':
        col = Lead.next_contact_date
        if sort_dir == 'desc':
            query = query.order_by(col.desc().nulls_last())
        else:
            query = query.order_by(col.asc().nulls_last())
    else:
        # Default sort: leads with a next_contact_date come first (soonest first),
        # then the rest ordered by created_at descending
        query = query.order_by(
            Lead.next_contact_date.asc().nulls_last(),
            Lead.created_at.desc()
        )
    pagination = get_page_items(query, page)

    return render_template(
        'leads/index.html',
        leads=pagination.items,
        pagination=pagination,
        search=search,
        status_filter=status_filter,
        score_filter=score_filter,
        contact_date_filter=contact_date_filter,
        statuses=LEAD_STATUSES,
        scores=LEAD_SCORES,
        today=date.today(),
        sort=sort,
        sort_dir=sort_dir,
        active_page='leads'
    )

@lead_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add a new lead."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        contact = request.form.get('contact_number', '').strip()
        email = request.form.get('email_id', '').strip() or None
        
        if not name or not contact:
            flash('Name and contact number are required.', 'danger')
            return redirect(url_for('leads.add'))
            
        duplicate = Lead.query.filter_by(contact_number=contact).first()
        if duplicate:
            flash(f'Lead with contact {contact} already exists.', 'warning')
            return redirect(url_for('leads.add'))
            
        lead = Lead(
            name=name,
            contact_number=contact,
            email_id=email,
            source=request.form.get('source', 'Organic'),
            score=request.form.get('score', 'Warm'),
            status=request.form.get('status', 'New'),
            contacted_by=request.form.get('contacted_by', '').strip() or None,
            notes=request.form.get('notes', '').strip()
        )

        # Next contact date
        ncd_raw = request.form.get('next_contact_date', '').strip()
        if ncd_raw:
            from datetime import date as _date
            try:
                lead.next_contact_date = _date.fromisoformat(ncd_raw)
            except ValueError:
                pass
        
        # Check if referral
        referrer_id = request.form.get('referred_by_id')
        if referrer_id and referrer_id.isdigit():
            lead.referred_by_id = int(referrer_id)
            lead.source = 'Referral'

        try:
            db.session.add(lead)
            db.session.commit()
            log_activity(current_user.username, 'Add', 'Lead', lead.lead_id, f'Added Lead {lead.name}', request.remote_addr)
            
            # Fire Meta CAPI for new Lead (Lead event)
            send_conversion_event(lead, event_name="Lead")
            
            flash('Lead created successfully!', 'success')
            return redirect(url_for('leads.view', lead_id=lead.lead_id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Error adding lead: {e}', exc_info=True)
            flash(f'Error: {e}', 'danger')

    # Fetch customers for referrer dropdown
    customers = Customer.query.filter_by(customer_status='Active').order_by(Customer.cust_name).all()
    return render_template('leads/add.html', sources=LEAD_SOURCES, scores=LEAD_SCORES, statuses=LEAD_STATUSES, customers=customers, active_page='leads')

@lead_bp.route('/<int:lead_id>')
@login_required
def view(lead_id):
    """View lead details."""
    from datetime import date
    lead = db.get_or_404(Lead, lead_id)
    wa_link = get_lead_followup_link(lead.name, lead.contact_number)
    return render_template('leads/view.html', lead=lead, wa_link=wa_link, today=date.today(), active_page='leads')

@lead_bp.route('/<int:lead_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(lead_id):
    """Edit lead details."""
    lead = db.get_or_404(Lead, lead_id)
    
    if request.method == 'POST':
        lead.name = request.form.get('name', '').strip()
        lead.contact_number = request.form.get('contact_number', '').strip()
        lead.email_id = request.form.get('email_id', '').strip() or None
        lead.source = request.form.get('source', lead.source)
        lead.score = request.form.get('score', lead.score)
        lead.status = request.form.get('status', lead.status)
        lead.contacted_by = request.form.get('contacted_by', '').strip() or None
        lead.notes = request.form.get('notes', '').strip()

        # Next contact date
        ncd_raw = request.form.get('next_contact_date', '').strip()
        if ncd_raw:
            from datetime import date as _date
            try:
                lead.next_contact_date = _date.fromisoformat(ncd_raw)
            except ValueError:
                pass
        else:
            lead.next_contact_date = None
        
        referrer_id = request.form.get('referred_by_id')
        if referrer_id and referrer_id.isdigit():
            lead.referred_by_id = int(referrer_id)
        else:
            lead.referred_by_id = None
            
        try:
            db.session.commit()
            log_activity(current_user.username, 'Edit', 'Lead', lead.lead_id, f'Updated Lead {lead.name}', request.remote_addr)
            flash('Lead updated successfully!', 'success')
            return redirect(url_for('leads.view', lead_id=lead.lead_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating lead: {e}', 'danger')

    customers = Customer.query.filter_by(customer_status='Active').order_by(Customer.cust_name).all()
    return render_template('leads/edit.html', lead=lead, sources=LEAD_SOURCES, scores=LEAD_SCORES, statuses=LEAD_STATUSES, customers=customers, active_page='leads')

@lead_bp.route('/<int:lead_id>/convert', methods=['GET', 'POST'])
@login_required
def convert(lead_id):
    """Convert a lead to a customer."""
    lead = db.get_or_404(Lead, lead_id)
    
    if lead.status == 'Converted':
        flash('This lead is already converted.', 'info')
        return redirect(url_for('leads.view', lead_id=lead.lead_id))

    if request.method == 'POST':
        try:
            plan = db.get_or_404(Plan, int(request.form['plan_id']))
            # Customer fields from form logic (simplified)
            # It redirects to standard customer creation page pre-filled
            pass
        except Exception as e:
            flash(f'Error: {e}', 'danger')

    # To keep it robust, we'll just redirect to the customer add page and pre-populate via session or URL params
    # But doing it via URL params is simpler
    url_params = {
        'from_lead': lead.lead_id,
        'cust_name': lead.name,
        'contact_number': lead.contact_number,
        'email_id': lead.email_id or '',
        'referred_by_id': lead.referred_by_id or ''
    }
    return redirect(url_for('customers.add', **url_params))

@lead_bp.route('/<int:lead_id>/mark_converted', methods=['POST'])
@login_required
def mark_converted(lead_id):
    """Internal API called when customer is actually created from lead."""
    lead = db.session.get(Lead, lead_id)
    if lead:
        lead.status = 'Converted'
        db.session.commit()
        # Fire Meta CAPI (Purchase / CompleteRegistration)
        send_conversion_event(lead, event_name="Purchase")
    return redirect(url_for('leads.index'))
