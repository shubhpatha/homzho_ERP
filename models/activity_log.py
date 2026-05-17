"""
models/activity_log.py - Tracks all user actions in the system.
"""
from datetime import datetime
from extensions import db


class ActivityLog(db.Model):
    """Stores audit trail for all user actions."""
    __tablename__ = 'activity_logs'

    log_id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(100), nullable=False)
    action_type = db.Column(db.String(30), nullable=False)  # Add, Edit, Delete, Login, Upload
    module_name = db.Column(db.String(50), nullable=False)   # Customer, Payment, Machine, etc.
    record_id = db.Column(db.Integer, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    remarks = db.Column(db.Text)
    ip_address = db.Column(db.String(45))  # Supports IPv6

    def __repr__(self):
        return f'<ActivityLog {self.action_type} {self.module_name} by {self.user_name}>'
