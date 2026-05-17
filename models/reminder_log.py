"""
models/reminder_log.py - Billing and maintenance reminder tracking.
"""
from datetime import datetime
from extensions import db


class ReminderLog(db.Model):
    """Tracks billing and maintenance reminders sent to customers."""
    __tablename__ = 'reminder_logs'

    reminder_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.cust_id'), nullable=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.machine_id'), nullable=True)
    reminder_type = db.Column(db.String(30), nullable=False)  # Billing, Maintenance
    scheduled_date = db.Column(db.Date, nullable=False)
    sent_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='Pending')  # Pending, Sent, Failed
    remarks = db.Column(db.Text)
    sent_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    machine = db.relationship('Machine', backref='reminder_logs', foreign_keys=[machine_id])

    def __repr__(self):
        return f'<ReminderLog {self.reminder_type} status={self.status}>'
