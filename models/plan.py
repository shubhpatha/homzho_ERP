"""
models/plan.py - Rental plan master data.
"""
from datetime import datetime
from extensions import db
from utils.tax import (
    CGST_RATE as PLAN_CGST_RATE,
    SGST_RATE as PLAN_SGST_RATE,
    calculate_inclusive_gst,
)


class Plan(db.Model):
    """Master rental plan used to populate customer forms."""
    __tablename__ = 'plans'
    CGST_RATE = PLAN_CGST_RATE
    SGST_RATE = PLAN_SGST_RATE

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
        return calculate_inclusive_gst(self.cost)['taxable_amount']

    @property
    def cgst_amount(self):
        return calculate_inclusive_gst(self.cost)['cgst_amount']

    @property
    def sgst_amount(self):
        return calculate_inclusive_gst(self.cost)['sgst_amount']

    @property
    def total_gst_amount(self):
        return calculate_inclusive_gst(self.cost)['total_tax_amount']

    def __repr__(self):
        return f'<Plan {self.plan_name}>'
