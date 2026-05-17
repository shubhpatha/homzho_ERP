"""
models/expense.py - Business expense records.
"""
from datetime import datetime
from extensions import db


class Expense(db.Model):
    """Business expense record with optional bill image."""
    __tablename__ = 'expenses'

    expense_id = db.Column(db.Integer, primary_key=True)
    expense_date = db.Column(db.Date, nullable=False, index=True)
    expense_category = db.Column(db.String(50), nullable=False)
    # Categories: Fuel, Technician, Marketing, Office, Repair, Misc
    amount = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(30), nullable=False)  # Cash, UPI, Bank Transfer
    paid_to = db.Column(db.String(150))
    bill_image = db.Column(db.String(500))  # Relative path to image
    remarks = db.Column(db.Text)
    approved_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Expense {self.expense_category} ₹{self.amount} on {self.expense_date}>'
