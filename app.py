"""
app.py - Homzho ERP Application Entry Point
Flask application factory pattern for PythonAnywhere compatibility.
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify
from config import config
from extensions import db, login_manager, migrate, csrf


def create_app(config_name: str = None) -> Flask:
    """Application factory — creates and configures the Flask app."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))

    # -----------------------------------------------------------------------
    # Ensure required directories exist
    # -----------------------------------------------------------------------
    for folder in [
        app.config['UPLOAD_FOLDER'],
        app.config['EXPORT_FOLDER'],
        app.config['BACKUP_FOLDER'],
        app.config['LOG_FOLDER'],
        os.path.join(app.config['UPLOAD_FOLDER'], 'customers'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'maintenance'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'expenses'),
    ]:
        os.makedirs(folder, exist_ok=True)

    # -----------------------------------------------------------------------
    # Logging setup (RotatingFileHandler — 5 × 1 MB)
    # -----------------------------------------------------------------------
    _setup_logging(app)

    # -----------------------------------------------------------------------
    # Initialize extensions
    # -----------------------------------------------------------------------
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # -----------------------------------------------------------------------
    # Flask-Login user loader
    # -----------------------------------------------------------------------
    from models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # -----------------------------------------------------------------------
    # Register Blueprints
    # -----------------------------------------------------------------------
    from routes.auth_routes import auth_bp
    from routes.dashboard_routes import dashboard_bp
    from routes.customer_routes import customer_bp
    from routes.payment_routes import payment_bp
    from routes.machine_routes import machine_bp
    from routes.maintenance_routes import maintenance_bp
    from routes.expense_routes import expense_bp
    from routes.accounting_routes import accounting_bp
    from routes.inventory_routes import inventory_bp
    from routes.upload_routes import upload_bp
    from routes.reminder_routes import reminder_bp
    from routes.report_routes import report_bp
    from routes.settings_routes import settings_bp
    from routes.lead_routes import lead_bp
    from routes.employee_routes import employee_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(machine_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(expense_bp)
    app.register_blueprint(accounting_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(reminder_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(lead_bp)
    app.register_blueprint(employee_bp)

    # -----------------------------------------------------------------------
    # Global Search endpoint
    # -----------------------------------------------------------------------
    from models.customer import Customer
    from models.payment import Payment
    from models.machine import Machine

    # -----------------------------------------------------------------------
    # Handle favicon.ico to prevent 404 logs
    # -----------------------------------------------------------------------
    @app.route('/favicon.ico')
    def favicon():
        return '', 204

    @app.route('/search')
    def global_search():
        from flask_login import current_user
        if not current_user.is_authenticated:
            return jsonify([])
        q = request.args.get('q', '').strip()
        if len(q) < 2:
            return jsonify([])

        results = []
        like = f'%{q}%'

        customers = Customer.query.filter(
            db.or_(
                Customer.cust_name.ilike(like),
                Customer.contact_number.ilike(like),
                Customer.email_id.ilike(like),
                Customer.machine_serial_no.ilike(like),
            )
        ).limit(5).all()
        for c in customers:
            results.append({'type': 'Customer', 'label': c.cust_name,
                            'sub': c.contact_number,
                            'url': f'/customers/{c.cust_id}'})

        payments = Payment.query.filter(
            db.or_(
                Payment.invoice_no.ilike(like),
                Payment.transaction_id.ilike(like),
            )
        ).limit(3).all()
        for p in payments:
            results.append({'type': 'Payment', 'label': p.invoice_no,
                            'sub': f'₹{p.amount_paid}',
                            'url': f'/payments/{p.payment_id}'})

        machines = Machine.query.filter(
            db.or_(
                Machine.machine_serial_no.ilike(like),
                Machine.model_name.ilike(like),
            )
        ).limit(3).all()
        for m in machines:
            results.append({'type': 'Machine', 'label': m.machine_serial_no,
                            'sub': m.model_name,
                            'url': f'/machines/{m.machine_id}'})

        return jsonify(results)

    # -----------------------------------------------------------------------
    # Error Handlers
    # -----------------------------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error(f'500 error: {e}', exc_info=True)
        return render_template('errors/500.html'), 500

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({'error': 'File too large. Maximum allowed size is 50 MB.'}), 413

    # -----------------------------------------------------------------------
    # Template context processors (inject helpers into all templates)
    # -----------------------------------------------------------------------
    @app.context_processor
    def inject_globals():
        from datetime import date
        return {
            'today': date.today(),
            'app_name': 'Homzho ERP',
        }

    # Create any missing lightweight master tables and seed defaults.
    with app.app_context():
        _ensure_user_permissions_column()
        _ensure_payment_invoice_columns()
        _ensure_default_plans()
        _ensure_leads_and_referrals()
        _ensure_employees_tables()
        _ensure_employee_links()
        _ensure_accounting_and_inventory()

    return app


def _ensure_user_permissions_column():
    """Add custom permission storage for existing SQLite installs."""
    from sqlalchemy import inspect, text

    db.create_all()
    inspector = inspect(db.engine)
    columns = {col['name'] for col in inspector.get_columns('users')}
    if 'custom_permissions' not in columns:
        db.session.execute(text('ALTER TABLE users ADD COLUMN custom_permissions TEXT'))
        db.session.commit()


def _ensure_payment_invoice_columns():
    """Add editable invoice fields for existing SQLite installs."""
    from sqlalchemy import inspect, text

    db.create_all()
    inspector = inspect(db.engine)
    columns = {col['name'] for col in inspector.get_columns('payments')}
    changed = False
    if 'invoice_items_json' not in columns:
        db.session.execute(text('ALTER TABLE payments ADD COLUMN invoice_items_json TEXT'))
        changed = True
    if 'deposit_amount' not in columns:
        db.session.execute(
            text('ALTER TABLE payments ADD COLUMN deposit_amount FLOAT NOT NULL DEFAULT 0')
        )
        changed = True
    if 'is_gst_invoice' not in columns:
        db.session.execute(
            text('ALTER TABLE payments ADD COLUMN is_gst_invoice BOOLEAN NOT NULL DEFAULT 1')
        )
        changed = True
    if changed:
        db.session.commit()


def _ensure_default_plans():
    """Ensure the plan master exists with the default Homzho plans."""
    from models.plan import Plan

    db.create_all()
    defaults = [
        ('Homzho Rental Monthly', 30, 399),
        ('Homzho Rental Yearly', 360, 4389),
        ('Homzho Rental Half Yearly', 180, 2349),
        ('Homzho Rental Quarterly', 90, 1197),
    ]
    changed = False
    for name, validity, cost in defaults:
        plan = Plan.query.filter_by(plan_name=name).first()
        if not plan:
            db.session.add(Plan(plan_name=name, validity_in_days=validity, cost=cost))
            changed = True
    if changed:
        db.session.commit()


def _ensure_leads_and_referrals():
    """Ensure the leads table exists and all new columns are present."""
    from sqlalchemy import inspect, text

    db.create_all()  # Creates leads table if it doesn't exist
    inspector = inspect(db.engine)

    # Add referred_by_id to customers if missing
    if 'customers' in inspector.get_table_names():
        columns = {col['name'] for col in inspector.get_columns('customers')}
        if 'referred_by_id' not in columns:
            try:
                db.session.execute(text('ALTER TABLE customers ADD COLUMN referred_by_id INTEGER REFERENCES customers(cust_id)'))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Migration error for referred_by_id: {e}")

    # Add next_contact_date to leads if missing
    if 'leads' in inspector.get_table_names():
        lead_columns = {col['name'] for col in inspector.get_columns('leads')}
        if 'next_contact_date' not in lead_columns:
            try:
                db.session.execute(text('ALTER TABLE leads ADD COLUMN next_contact_date DATE'))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Migration error for next_contact_date: {e}")


def _ensure_accounting_and_inventory():
    """Create new accounting/inventory tables and backfill ledger rows."""
    from models import AccountLedger, InventoryItem, InventoryMovement  # noqa: F401
    from services.accounting_service import backfill_account_ledger

    db.create_all()
    backfill_account_ledger()
    db.session.commit()


def _ensure_employees_tables():
    """Create employees, attendance_logs, and salary_records tables if not present."""
    from models.employee import Employee, AttendanceLog, SalaryRecord  # noqa: F401
    db.create_all()


def _ensure_employee_links():
    """
    Safely add installed_by_emp_id to customers and technician_emp_id to maintenance
    if they do not already exist (safe for existing SQLite databases).
    """
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    changed = False

    # customers table
    if 'customers' in inspector.get_table_names():
        cust_cols = {c['name'] for c in inspector.get_columns('customers')}
        if 'installed_by_emp_id' not in cust_cols:
            db.session.execute(text(
                'ALTER TABLE customers ADD COLUMN installed_by_emp_id INTEGER REFERENCES employees(emp_id)'
            ))
            changed = True

    # maintenance table
    if 'maintenance' in inspector.get_table_names():
        maint_cols = {c['name'] for c in inspector.get_columns('maintenance')}
        if 'technician_emp_id' not in maint_cols:
            db.session.execute(text(
                'ALTER TABLE maintenance ADD COLUMN technician_emp_id INTEGER REFERENCES employees(emp_id)'
            ))
            changed = True

    if changed:
        db.session.commit()

def _setup_logging(app: Flask):
    """Configure rotating file logger."""
    log_dir = app.config['LOG_FOLDER']
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'error.log')

    level = logging.DEBUG if app.config.get('DEBUG') else logging.ERROR
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )

    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    app.logger.setLevel(level)
    app.logger.addHandler(file_handler)


# ---------------------------------------------------------------------------
# Application instance (for PythonAnywhere WSGI)
# ---------------------------------------------------------------------------
app = create_app()


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------
import click

@app.cli.command('create-admin')
@click.option('--email', prompt='Admin email', help='Email address for the admin user')
@click.option('--password', prompt=True, hide_input=True,
              confirmation_prompt=True, help='Admin password')
@click.option('--username', default='admin', help='Username (default: admin)')
@click.option('--fullname', default='Administrator', help='Full name')
def create_admin(email, password, username, fullname):
    """Create the first admin user via CLI."""
    from models.user import User
    if User.query.filter_by(role='admin').first():
        click.echo('⚠️  An admin user already exists. Aborting.')
        return
    user = User(
        username=username,
        email=email.lower(),
        full_name=fullname,
        role='admin',
        is_active=True,
    )
    user.set_password(password)
    with app.app_context():
        db.session.add(user)
        db.session.commit()
        # Create setup complete flag
        flag = os.path.join(os.path.dirname(__file__), '.setup_complete')
        open(flag, 'w').close()
    click.echo(f'✅  Admin user "{username}" created successfully.')


@app.cli.command('update-statuses')
def update_statuses():
    """Update expired customer statuses (run daily via cron)."""
    from datetime import date
    from models.customer import Customer
    today = date.today()
    expired = Customer.query.filter(
        Customer.customer_status == 'Active',
        Customer.plan_end_date < today,
    ).all()
    count = 0
    for c in expired:
        c.customer_status = 'Expired'
        count += 1
    db.session.commit()
    click.echo(f'✅  Updated {count} customers to Expired status.')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
