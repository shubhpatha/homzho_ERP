"""
models/customer.py - Customer model with all rental plan details.
"""
from datetime import datetime
from dateutil.relativedelta import relativedelta
from extensions import db


class Customer(db.Model):
    """Customer record including rental plan and machine assignment."""
    __tablename__ = 'customers'

    cust_id = db.Column(db.Integer, primary_key=True)
    cust_name = db.Column(db.String(150), nullable=False, index=True)
    contact_number = db.Column(db.String(15), unique=True, nullable=False, index=True)
    email_id = db.Column(db.String(120), unique=True, nullable=True)

    # Rental plan details
    plan_name = db.Column(db.String(100), nullable=False)
    plan_duration_months = db.Column(db.Integer, default=12, nullable=False)
    plan_start_date = db.Column(db.Date, nullable=False)
    plan_end_date = db.Column(db.Date, nullable=True)  # Auto-calculated
    payment_freq = db.Column(db.String(30), default='Monthly')  # Monthly, Quarterly, Annual
    monthly_rent = db.Column(db.Float, nullable=False)

    # Deposit management
    deposit = db.Column(db.Float, default=0.0)
    deposit_refunded = db.Column(db.Boolean, default=False)
    deposit_refund_date = db.Column(db.Date, nullable=True)
    deposit_refund_amount = db.Column(db.Float, nullable=True)
    refund_remark = db.Column(db.Text, nullable=True)

    # Status
    customer_status = db.Column(db.String(20), nullable=False, default='Active')
    # Statuses: Active, Inactive, Expired, Cancelled
    contract_end_date = db.Column(db.Date, nullable=True)
    contract_end_reason = db.Column(db.Text, nullable=True)

    # Address
    address = db.Column(db.Text)
    area = db.Column(db.String(150), index=True)   # Locality / neighbourhood
    city = db.Column(db.String(100), index=True)
    pin = db.Column(db.String(10))

    # Machine assignment
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.machine_id'), nullable=True)
    machine_serial_no = db.Column(db.String(100))
    installed_by = db.Column(db.String(100))  # Legacy text field kept for backward compat
    installed_by_emp_id = db.Column(db.Integer, db.ForeignKey('employees.emp_id'), nullable=True)
    installation_date = db.Column(db.Date, nullable=True)
    installation_cost = db.Column(db.Float, default=0.0)

    # Service tracking
    last_service_date = db.Column(db.Date, nullable=True)
    # next_service_date is no longer stored here — it reads from machine.
    # See @property below.
    next_billing_date = db.Column(db.Date, nullable=True)
    
    # Referral Tracking
    referred_by_id = db.Column(db.Integer, db.ForeignKey('customers.cust_id'), nullable=True)
    referrer = db.relationship('Customer', remote_side=[cust_id], foreign_keys=[referred_by_id], backref='referrals')

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    payments = db.relationship('Payment', backref='customer', lazy='dynamic',
                                foreign_keys='Payment.customer_id')
    uploads = db.relationship('Upload', backref='customer', lazy='dynamic',
                               foreign_keys='Upload.customer_id')
    reminder_logs = db.relationship('ReminderLog', backref='customer', lazy='dynamic',
                                     foreign_keys='ReminderLog.customer_id')
    # machine assigned relationship
    machine = db.relationship('Machine', backref='customers',
                               foreign_keys=[machine_id])
    # installer employee relationship
    installer = db.relationship('Employee', foreign_keys=[installed_by_emp_id],
                                backref='installations')

    def calculate_plan_end_date(self):
        """Auto-calculate plan_end_date from start date + duration."""
        if self.plan_start_date and self.plan_duration_months:
            self.plan_end_date = self.plan_start_date + relativedelta(months=self.plan_duration_months)

    @property
    def next_service_date(self):
        """Single source of truth: reads next_service_date from the assigned machine.

        Backward-compatible — any template or route that reads
        ``customer.next_service_date`` continues to work unchanged.
        Returns None when no machine is assigned.
        """
        if self.machine:
            return self.machine.next_service_date
        return None

    def __repr__(self):
        return f'<Customer {self.cust_id} - {self.cust_name}>'
