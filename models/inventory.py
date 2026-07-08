"""
models/inventory.py - Stock items and movement history.
"""
from datetime import datetime
from extensions import db


class InventoryItem(db.Model):
    """Inventory item such as filters, fittings, tools, or spares."""
    __tablename__ = 'inventory_items'

    item_id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(150), nullable=False, unique=True, index=True)
    category = db.Column(db.String(80), nullable=False, default='Spare Part')
    unit = db.Column(db.String(30), nullable=False, default='pcs')
    current_stock = db.Column(db.Float, nullable=False, default=0.0)
    reorder_level = db.Column(db.Float, nullable=False, default=0.0)
    unit_cost = db.Column(db.Float, nullable=False, default=0.0)
    vendor_name = db.Column(db.String(150))
    remarks = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    movements = db.relationship('InventoryMovement', backref='item', lazy='dynamic')

    @property
    def stock_value(self):
        return float(self.current_stock or 0) * float(self.unit_cost or 0)

    @property
    def is_low_stock(self):
        return float(self.current_stock or 0) <= float(self.reorder_level or 0)

    def __repr__(self):
        return f'<InventoryItem {self.item_name} ({self.current_stock} {self.unit})>'


class InventoryMovement(db.Model):
    """Audit trail for every stock increase or decrease."""
    __tablename__ = 'inventory_movements'

    movement_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.item_id'), nullable=False, index=True)
    movement_date = db.Column(db.Date, nullable=False, index=True)
    movement_type = db.Column(db.String(20), nullable=False)  # In, Out, Adjustment
    quantity = db.Column(db.Float, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False, default=0.0)
    reference_type = db.Column(db.String(50))
    reference_id = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def total_value(self):
        return float(self.quantity or 0) * float(self.unit_cost or 0)

    def __repr__(self):
        return f'<InventoryMovement {self.movement_type} Item#{self.item_id} {self.quantity}>'
