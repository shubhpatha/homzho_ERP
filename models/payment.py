"""
models/payment.py - Payment record with auto-generated invoice numbers.
"""
import json
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
    invoice_items_json = db.Column(db.Text, nullable=True)
    deposit_amount = db.Column(db.Float, nullable=False, default=0.0)
    payment_status = db.Column(db.String(20), nullable=False, default='Paid')
    # Statuses: Paid, Partial, Overdue, Pending
    days_overdue = db.Column(db.Integer, default=0)
    remark = db.Column(db.Text)
    collected_by = db.Column(db.String(100))
    next_due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def _as_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @property
    def invoice_items(self):
        """Return normalized editable invoice product/service rows."""
        if not self.invoice_items_json:
            return []
        try:
            raw_items = json.loads(self.invoice_items_json)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(raw_items, list):
            return []

        items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            description = str(item.get('description') or '').strip()
            quantity = self._as_float(item.get('quantity'), 1.0)
            unit_price = self._as_float(item.get('unit_price'), 0.0)
            line_total = self._as_float(item.get('line_total'), quantity * unit_price)
            if description and line_total >= 0:
                items.append({
                    'description': description,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'line_total': line_total,
                })
        return items

    @invoice_items.setter
    def invoice_items(self, items):
        clean_items = []
        for item in items or []:
            description = str(item.get('description') or '').strip()
            quantity = self._as_float(item.get('quantity'), 1.0)
            unit_price = self._as_float(item.get('unit_price'), 0.0)
            line_total = round(quantity * unit_price, 2)
            if description and quantity > 0 and unit_price >= 0:
                clean_items.append({
                    'description': description,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'line_total': line_total,
                })
        self.invoice_items_json = json.dumps(clean_items) if clean_items else None

    def __repr__(self):
        return f'<Payment {self.invoice_no} - ₹{self.amount_paid}>'
