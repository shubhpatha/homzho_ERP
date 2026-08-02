"""
models/maintenance.py - Machine maintenance/service records.
"""
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from extensions import db


class Maintenance(db.Model):
    """Service/maintenance record for a machine."""
    __tablename__ = 'maintenance'

    service_id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.machine_id'), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.cust_id'), nullable=True)
    service_date = db.Column(db.Date, nullable=False, index=True)
    next_service_date = db.Column(db.Date, nullable=True)   # Auto: service_date + next_service_months
    next_service_months = db.Column(db.Integer, default=3, nullable=False)  # Interval chosen at service time
    service_type = db.Column(db.String(80), nullable=False)  # Routine, Filter Change, Repair, etc.
    parts_replaced = db.Column(db.Text)
    filter_changed = db.Column(db.Boolean, default=False)
    technician_name = db.Column(db.String(100))  # Legacy text field kept for backward compat
    technician_emp_id = db.Column(db.Integer, db.ForeignKey('employees.emp_id'), nullable=True)
    water_tds = db.Column(db.Float, nullable=True)
    main_exp = db.Column(db.Float, default=0.0)    # Maintenance expense
    travel_exp = db.Column(db.Float, default=0.0)  # Travel expense
    customer_feedback = db.Column(db.String(30))   # Excellent, Good, Average, Poor
    remark = db.Column(db.Text)
    image_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Customer relationship (optional, for display)
    customer = db.relationship('Customer', backref='maintenance_records',
                                foreign_keys=[customer_id])
    # Technician employee relationship
    technician = db.relationship('Employee', foreign_keys=[technician_emp_id],
                                  backref='service_records')

    def set_next_service_date(self, months=3):
        """Calculate next service date = service_date + given months (default 3)."""
        if self.service_date:
            self.next_service_months = months
            self.next_service_date = self.service_date + relativedelta(months=months)

    def __repr__(self):
        return f'<Maintenance Machine#{self.machine_id} on {self.service_date}>'
