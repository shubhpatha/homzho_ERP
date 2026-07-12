"""
models/lead.py - Lead tracking model for prospective customers.
"""
from datetime import datetime
from extensions import db

class Lead(db.Model):
    """Represents a potential customer (Lead) before conversion."""
    __tablename__ = 'leads'

    lead_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    contact_number = db.Column(db.String(15), unique=True, nullable=False, index=True)
    email_id = db.Column(db.String(120), nullable=True)
    
    # Lead Source & Score
    source = db.Column(db.String(50), default='Organic') # e.g. Meta, Referral, Organic, Google
    score = db.Column(db.String(20), default='Warm') # Hot, Warm, Cold
    status = db.Column(db.String(30), default='New') # New, Contacted, Qualified, Lost, Converted
    
    # Referral Tracking
    referred_by_id = db.Column(db.Integer, db.ForeignKey('customers.cust_id'), nullable=True)
    
    contacted_by = db.Column(db.String(100), nullable=True)  # Staff member who contacted this lead
    notes = db.Column(db.Text)
    next_contact_date = db.Column(db.Date, nullable=True)  # Manually set follow-up date
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to referrer (Customer)
    referrer = db.relationship('Customer', foreign_keys=[referred_by_id])

    def __repr__(self):
        return f'<Lead {self.lead_id} - {self.name} ({self.score})>'
