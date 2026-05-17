"""
models/plan.py - Rental plan master data.
"""
from datetime import datetime
from extensions import db


class Plan(db.Model):
    """Master rental plan used to populate customer forms."""
    __tablename__ = 'plans'

    plan_id = db.Column(db.Integer, primary_key=True)
    plan_name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    validity_in_days = db.Column(db.Integer, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def duration_months(self):
        return max(1, round(self.validity_in_days / 30))

    @property
    def payment_frequency(self):
        if self.validity_in_days <= 30:
            return 'Monthly'
        if self.validity_in_days <= 90:
            return 'Quarterly'
        if self.validity_in_days <= 180:
            return 'Half Yearly'
        return 'Annual'

    def __repr__(self):
        return f'<Plan {self.plan_name}>'
