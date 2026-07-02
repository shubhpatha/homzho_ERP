"""
models/__init__.py - Import all models to make them available to Flask-Migrate.
"""
from models.user import User
from models.customer import Customer
from models.machine import Machine, MachineAssignmentHistory
from models.payment import Payment
from models.maintenance import Maintenance
from models.expense import Expense
from models.upload import Upload
from models.activity_log import ActivityLog
from models.reminder_log import ReminderLog
from models.plan import Plan
from models.lead import Lead
