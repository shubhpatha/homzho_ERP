"""
models/plan.py - Rental plan master data.
"""
from datetime import datetime
from extensions import db


class Plan(db.Model):
    """Master rental plan used to populate customer forms."""
    __tablename__ = 'plans'
    CGST_RATE = 0.09
    SGST_RATE = 0.09

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

    @property
    def taxable_cost(self):
        """Cost before GST when stored cost is GST-inclusive."""
        total_rate = self.CGST_RATE + self.SGST_RATE
        return (self.cost or 0) / (1 + total_rate)

    @property
    def cgst_amount(self):
        return self.taxable_cost * self.CGST_RATE

    @property
    def sgst_amount(self):
        return self.taxable_cost * self.SGST_RATE

    @property
    def total_gst_amount(self):
        return self.cgst_amount + self.sgst_amount

    def __repr__(self):
        return f'<Plan {self.plan_name}>'
