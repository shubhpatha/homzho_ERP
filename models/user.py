"""
models/user.py - User model with role-based access control.
"""
from datetime import datetime
import json
from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


ROLE_PERMISSIONS = {
    'admin': {
        'customers', 'machines', 'payments', 'maintenance', 'expenses',
        'uploads', 'reports', 'settings',
    },
    'operator': {'customers', 'machines', 'payments', 'maintenance', 'expenses', 'uploads', 'reports'},
    'technician': {'maintenance', 'machines'},
    'custom': set(),
}


class User(UserMixin, db.Model):
    """Application user with role-based access."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='operator')  # admin, operator, technician, custom
    custom_permissions = db.Column(db.Text, nullable=True)
    full_name = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        """Hash and store password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def is_operator(self):
        return self.role in ('admin', 'operator')

    def is_technician(self):
        return self.role in ('admin', 'technician') or self.has_permission('maintenance')

    def permission_set(self):
        if self.role != 'custom':
            return set(ROLE_PERMISSIONS.get(self.role, set()))
        if not self.custom_permissions:
            return set()
        try:
            return set(json.loads(self.custom_permissions))
        except (TypeError, ValueError):
            return set()

    def set_permissions(self, permissions):
        self.custom_permissions = json.dumps(sorted(set(permissions or [])))

    def has_permission(self, permission):
        return self.is_admin() or permission in self.permission_set()

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'
