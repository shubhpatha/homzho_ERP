"""
models/machine.py - Water purifier machine model.
"""
from datetime import datetime
from extensions import db


class Machine(db.Model):
    """Represents a water purifier machine in inventory."""
    __tablename__ = 'machines'

    machine_id = db.Column(db.Integer, primary_key=True)
    machine_serial_no = db.Column(db.String(100), unique=True, nullable=False, index=True)
    model_name = db.Column(db.String(100), nullable=False)
    machine_status = db.Column(db.String(30), nullable=False, default='Available')
    # Statuses: Available, Installed, Under Maintenance, Scrapped
    assigned_customer_id = db.Column(db.Integer, db.ForeignKey('customers.cust_id'), nullable=True)
    installation_date = db.Column(db.Date, nullable=True)
    last_service_date = db.Column(db.Date, nullable=True)
    next_service_date = db.Column(db.Date, nullable=True)
    machine_condition = db.Column(db.String(50))  # Good, Fair, Poor
    tds_level = db.Column(db.Float, nullable=True)
    filter_change_due = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    maintenance_records = db.relationship('Maintenance', backref='machine', lazy='dynamic')
    assignment_history = db.relationship('MachineAssignmentHistory', backref='machine', lazy='dynamic')
    uploads = db.relationship('Upload', backref='machine', lazy='dynamic', foreign_keys='Upload.machine_id')

    def __repr__(self):
        return f'<Machine {self.machine_serial_no} - {self.machine_status}>'


class MachineAssignmentHistory(db.Model):
    """Tracks machine assignment/unassignment history."""
    __tablename__ = 'machine_assignment_history'

    assignment_id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.machine_id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.cust_id'), nullable=False)
    assigned_on = db.Column(db.Date, nullable=False)
    returned_on = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.Text)

    # Relationship
    customer = db.relationship('Customer', backref='machine_assignments')

    def __repr__(self):
        return f'<Assignment Machine#{self.machine_id} -> Customer#{self.customer_id}>'
