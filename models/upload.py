"""
models/upload.py - File upload records linked to customers/machines.
"""
from datetime import datetime
from extensions import db


class Upload(db.Model):
    """File/image upload record linked to a customer or machine."""
    __tablename__ = 'uploads'

    upload_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.cust_id'), nullable=True, index=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.machine_id'), nullable=True)
    upload_type = db.Column(db.String(50), nullable=False)
    # Types: Installation, Service, Payment Proof, KYC, Other
    file_path = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(255))
    file_size = db.Column(db.Integer)   # In bytes
    remarks = db.Column(db.Text)
    uploaded_by = db.Column(db.String(100))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Upload {self.upload_type} for Customer#{self.customer_id}>'
