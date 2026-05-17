"""
models/payment.py - Payment record with auto-generated invoice numbers.
"""
from datetime import datetime
from extensions import db


class Payment(db.Model):
    """Payment transaction record."""
    __tablename__ = 'payments'

    payment_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.cust_id'), nullable=False, index=True)
    payment_date = db.Column(db.Date, nullable=False, index=True)
    amount_paid = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(30), nullable=False)  # Cash, UPI, Bank Transfer, Cheque
    transaction_id = db.Column(db.String(100), unique=True, nullable=True)
    invoice_no = db.Column(db.String(30), unique=True, nullable=False, index=True)
    amount_due = db.Column(db.Float, nullable=False)
    payment_status = db.Column(db.String(20), nullable=False, default='Paid')
    # Statuses: Paid, Partial, Overdue, Pending
    days_overdue = db.Column(db.Integer, default=0)
    remark = db.Column(db.Text)
    collected_by = db.Column(db.String(100))
    next_due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Payment {self.invoice_no} - ₹{self.amount_paid}>'
