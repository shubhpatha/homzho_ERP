"""
models/accounting.py - Unified accounting ledger for income and expenses.
"""
from datetime import datetime
from extensions import db


class AccountLedger(db.Model):
    """Single ledger row for money coming in or going out."""
    __tablename__ = 'account_ledger'

    ledger_id = db.Column(db.Integer, primary_key=True)
    entry_date = db.Column(db.Date, nullable=False, index=True)
    entry_type = db.Column(db.String(20), nullable=False, index=True)  # Income, Expense
    category = db.Column(db.String(80), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(30))
    party_name = db.Column(db.String(150))
    description = db.Column(db.Text)
    source_type = db.Column(db.String(40), nullable=False, index=True)
    source_id = db.Column(db.Integer, nullable=False, index=True)
    reference_no = db.Column(db.String(100), index=True)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            'source_type',
            'source_id',
            'entry_type',
            'category',
            name='uq_account_ledger_source_entry',
        ),
    )

    def __repr__(self):
        return f'<Ledger {self.entry_type} {self.category} Rs {self.amount}>'
