"""
models/employee.py - Employee, Attendance & Salary management models.

Covers both field technicians and office staff.
AttendanceLog supports flexible week-off days (not fixed per weekday) —
each attendance row can record whether that day was a week-off or not,
and bulk marking lets the admin choose week-off day(s) per week freely.
"""
from datetime import datetime, date
from extensions import db


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMPLOYEE_TYPES = [
    'Field Technician',
    'Office Staff',
    'Manager',
    'Driver',
    'Sales Executive',
    'Other',
]

ATTENDANCE_STATUSES = [
    'Present',
    'Absent',
    'Half Day',
    'Leave',
    'Week Off',
    'Holiday',
]

LEAVE_TYPES = [
    'Casual Leave',
    'Sick Leave',
    'Earned Leave',
    'Unpaid Leave',
]

SALARY_COMPONENTS = [
    'Basic Salary',
    'Advance',
    'Deduction',
    'Bonus',
    'Incentive',
    'Reimbursement',
]

PAYMENT_MODES = ['Cash', 'UPI', 'Bank Transfer', 'Cheque']


# ---------------------------------------------------------------------------
# Employee Model
# ---------------------------------------------------------------------------

class Employee(db.Model):
    """HR record for an employee or field technician."""
    __tablename__ = 'employees'

    emp_id = db.Column(db.Integer, primary_key=True)

    # ---- Identity ----
    emp_name = db.Column(db.String(150), nullable=False, index=True)
    emp_code = db.Column(db.String(30), unique=True, nullable=True, index=True)  # e.g. HZ-T001
    emp_type = db.Column(db.String(50), nullable=False, default='Field Technician')
    department = db.Column(db.String(100), nullable=True)

    # ---- Contact ----
    contact_number = db.Column(db.String(15), nullable=False, index=True)
    emergency_contact = db.Column(db.String(15), nullable=True)
    emergency_contact_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True)

    # ---- Address ----
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    pin = db.Column(db.String(10), nullable=True)

    # ---- Employment ----
    join_date = db.Column(db.Date, nullable=False, default=date.today)
    exit_date = db.Column(db.Date, nullable=True)  # Null = still employed
    status = db.Column(db.String(20), nullable=False, default='Active')
    # Statuses: Active, Inactive, On Leave, Resigned, Terminated

    # ---- Salary ----
    monthly_salary = db.Column(db.Float, nullable=False, default=0.0)
    salary_payment_mode = db.Column(db.String(30), default='Cash')
    bank_account_no = db.Column(db.String(30), nullable=True)
    bank_name = db.Column(db.String(100), nullable=True)
    upi_id = db.Column(db.String(100), nullable=True)

    # ---- Identity Docs ----
    aadhar_no = db.Column(db.String(20), nullable=True)
    pan_no = db.Column(db.String(20), nullable=True)

    # ---- Optional app user link ----
    # If the employee also has an app login, link them here (optional)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ---- Relationships ----
    attendance_logs = db.relationship(
        'AttendanceLog', backref='employee', lazy='dynamic',
        foreign_keys='AttendanceLog.emp_id',
        cascade='all, delete-orphan',
    )
    salary_records = db.relationship(
        'SalaryRecord', backref='employee', lazy='dynamic',
        foreign_keys='SalaryRecord.emp_id',
        cascade='all, delete-orphan',
    )
    linked_user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<Employee {self.emp_id} - {self.emp_name} ({self.emp_type})>'

    @property
    def is_active(self):
        return self.status == 'Active'

    def attendance_summary(self, month: int, year: int):
        """Return a dict with Present/Absent/Half Day counts for a given month."""
        logs = self.attendance_logs.filter(
            db.extract('month', AttendanceLog.att_date) == month,
            db.extract('year', AttendanceLog.att_date) == year,
        ).all()
        counts = {s: 0 for s in ATTENDANCE_STATUSES}
        for log in logs:
            if log.status in counts:
                counts[log.status] += 1
        counts['_total_marked'] = len(logs)
        return counts

    def net_salary_for_month(self, month: int, year: int):
        """Return net payable for a month = Basic - Deductions + Bonuses - Advances paid."""
        records = self.salary_records.filter(
            db.extract('month', SalaryRecord.record_date) == month,
            db.extract('year', SalaryRecord.record_date) == year,
        ).all()
        total = 0.0
        for r in records:
            if r.component in ('Basic Salary', 'Bonus', 'Incentive', 'Reimbursement'):
                total += r.amount
            elif r.component in ('Deduction', 'Advance'):
                total -= r.amount
        return total


# ---------------------------------------------------------------------------
# Attendance Log
# ---------------------------------------------------------------------------

class AttendanceLog(db.Model):
    """
    Daily attendance record for one employee.

    Week-off days are FLEXIBLE — the admin marks any day as 'Week Off'
    regardless of which weekday it falls on. This supports rotating
    schedules, varying weekly offs, and ad-hoc holiday substitutions.
    """
    __tablename__ = 'attendance_logs'

    att_id = db.Column(db.Integer, primary_key=True)
    emp_id = db.Column(db.Integer, db.ForeignKey('employees.emp_id'), nullable=False, index=True)
    att_date = db.Column(db.Date, nullable=False, index=True)

    # Core status — includes 'Week Off' as a valid daily status
    status = db.Column(db.String(20), nullable=False, default='Present')
    # Present | Absent | Half Day | Leave | Week Off | Holiday

    # Optional leave type (only relevant when status == 'Leave')
    leave_type = db.Column(db.String(30), nullable=True)

    # Optional time tracking
    check_in = db.Column(db.String(10), nullable=True)   # 'HH:MM' string
    check_out = db.Column(db.String(10), nullable=True)

    # Optional notes / reason
    notes = db.Column(db.Text, nullable=True)

    marked_by = db.Column(db.String(80), nullable=True)  # username who marked it
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one record per employee per day
    __table_args__ = (
        db.UniqueConstraint('emp_id', 'att_date', name='uq_employee_date'),
    )

    def __repr__(self):
        return f'<Attendance Emp#{self.emp_id} {self.att_date} - {self.status}>'


# ---------------------------------------------------------------------------
# Salary Record
# ---------------------------------------------------------------------------

class SalaryRecord(db.Model):
    """
    Individual salary component entry (payment, advance, deduction, bonus).

    One employee can have multiple SalaryRecord entries per month
    (e.g., one for Basic Salary, one for Advance, one for Bonus).
    """
    __tablename__ = 'salary_records'

    record_id = db.Column(db.Integer, primary_key=True)
    emp_id = db.Column(db.Integer, db.ForeignKey('employees.emp_id'), nullable=False, index=True)

    record_date = db.Column(db.Date, nullable=False, index=True)  # Date of transaction
    component = db.Column(db.String(50), nullable=False)  # Basic Salary / Advance / Deduction / Bonus
    amount = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(30), default='Cash')
    reference_no = db.Column(db.String(100), nullable=True)  # UTR / Cheque no
    remarks = db.Column(db.Text, nullable=True)

    paid_by = db.Column(db.String(80), nullable=True)  # username who recorded it
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SalaryRecord Emp#{self.emp_id} {self.component} ₹{self.amount} on {self.record_date}>'
