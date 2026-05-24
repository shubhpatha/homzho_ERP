"""
routes/settings_routes.py - App settings, user management, backup/restore.
"""
import os
import re
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, send_file, current_app)
from flask_login import login_required, current_user
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from models.user import User, ROLE_PERMISSIONS
from models.activity_log import ActivityLog
from models.plan import Plan
from utils.helpers import log_activity
from utils.backup_utils import create_backup, list_backups, restore_backup

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

ALLOWED_DB_OPERATIONS = {'select', 'insert', 'update', 'delete'}
READ_PREVIEW_LIMIT = 100


def admin_required(f):
    """Decorator: admin-only access."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin():
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


def _find_statement_semicolons(sql):
    """Return semicolons that are outside simple quoted SQL strings."""
    semicolons = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < len(sql) else ''
        if char == "'" and not in_double:
            if in_single and next_char == "'":
                i += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            if in_double and next_char == '"':
                i += 2
                continue
            in_double = not in_double
        elif char == ';' and not in_single and not in_double:
            semicolons.append(i)
        i += 1
    return semicolons


def _normalise_sql(sql):
    """Validate one admin SQL statement and return (statement, operation)."""
    statement = (sql or '').strip()
    if not statement:
        raise ValueError('Enter a SQL statement.')

    semicolons = _find_statement_semicolons(statement)
    if semicolons:
        first_semicolon = semicolons[0]
        if len(semicolons) > 1 or statement[first_semicolon + 1:].strip():
            raise ValueError('Run one SQL statement at a time.')
        statement = statement[:first_semicolon].strip()

    allowed_pattern = '|'.join(sorted(ALLOWED_DB_OPERATIONS))
    match = re.match(rf'^({allowed_pattern})\b', statement, re.IGNORECASE)
    if not match:
        raise ValueError('Only SELECT, INSERT, UPDATE, and DELETE statements are allowed.')

    return statement, match.group(1).lower()


def _clean_identifier(identifier):
    """Normalise a simple table identifier extracted from SQL."""
    cleaned = identifier.strip().strip('`"[]')
    if '.' in cleaned:
        cleaned = cleaned.split('.')[-1].strip('`"[]')
    return cleaned


def _extract_write_table(operation, statement):
    patterns = {
        'insert': r'^\s*insert\s+(?:or\s+\w+\s+)?into\s+([`"\[]?[\w.]+[`"\]]?)',
        'update': r'^\s*update\s+(?:or\s+\w+\s+)?([`"\[]?[\w.]+[`"\]]?)',
        'delete': r'^\s*delete\s+from\s+([`"\[]?[\w.]+[`"\]]?)',
    }
    match = re.match(patterns[operation], statement, re.IGNORECASE)
    return _clean_identifier(match.group(1)) if match else None


def _schema_snapshot():
    """Return table metadata for the database console."""
    inspector = inspect(db.engine)
    preparer = db.engine.dialect.identifier_preparer
    tables = []

    for table_name in inspector.get_table_names():
        if table_name.startswith('sqlite_'):
            continue

        row_count = None
        try:
            quoted_table = preparer.quote(table_name)
            row_count = db.session.connection().exec_driver_sql(
                f'SELECT COUNT(*) FROM {quoted_table}'
            ).scalar()
        except SQLAlchemyError:
            db.session.rollback()

        columns = []
        for column in inspector.get_columns(table_name):
            columns.append({
                'name': column['name'],
                'type': str(column['type']),
                'nullable': column.get('nullable', True),
                'primary_key': bool(column.get('primary_key')),
                'default': column.get('default'),
            })

        tables.append({
            'name': table_name,
            'row_count': row_count,
            'columns': columns,
        })

    return sorted(tables, key=lambda item: item['name'])


def _validate_write_table(operation, statement, existing_tables):
    target_table = _extract_write_table(operation, statement)
    if not target_table or target_table not in existing_tables:
        raise ValueError('Write queries must target an existing application table.')
    if target_table.startswith('sqlite_'):
        raise ValueError('SQLite internal tables cannot be modified here.')
    return target_table


def _run_database_statement(statement, operation):
    result = db.session.connection().exec_driver_sql(statement)

    if operation == 'select':
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchmany(READ_PREVIEW_LIMIT)]
        return {
            'operation': operation.upper(),
            'columns': columns,
            'rows': rows,
            'row_count': len(rows),
            'preview_limit': READ_PREVIEW_LIMIT,
            'rows_affected': None,
        }

    db.session.commit()
    return {
        'operation': operation.upper(),
        'columns': [],
        'rows': [],
        'row_count': 0,
        'preview_limit': READ_PREVIEW_LIMIT,
        'rows_affected': result.rowcount,
    }


# ---------------------------------------------------------------------------
# Settings Home
# ---------------------------------------------------------------------------

@settings_bp.route('/')
@login_required
@admin_required
def index():
    users = User.query.order_by(User.created_at.desc()).all()
    backups = list_backups()
    recent_logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(50).all()
    return render_template('settings/index.html', users=users, backups=backups,
                           recent_logs=recent_logs,
                           permission_options=[
                               ('customers', 'Customers'),
                               ('machines', 'Machines'),
                               ('payments', 'Payments'),
                               ('maintenance', 'Maintenance'),
                               ('expenses', 'Expenses'),
                               ('uploads', 'Uploads'),
                               ('reports', 'Reports'),
                           ],
                           role_permissions=ROLE_PERMISSIONS,
                           active_page='settings')


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

@settings_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    """Add a new user."""
    if request.method == 'POST':
        try:
            role = request.form.get('role', 'operator').strip().lower()
            user = User(
                username=request.form['username'].strip(),
                email=request.form['email'].strip().lower(),
                full_name=request.form.get('full_name', '').strip(),
                role=role,
                is_active=True,
            )
            if role == 'custom':
                user.set_permissions(request.form.getlist('permissions'))
            user.set_password(request.form['password'])
            db.session.add(user)
            db.session.commit()
            log_activity(current_user.username, 'Add', 'User', user.id,
                         f'Added user: {user.username}', request.remote_addr)
            flash(f'User "{user.username}" created!', 'success')
            return redirect(url_for('settings.index'))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding user: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    return render_template('settings/add_user.html', active_page='settings')


@settings_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    """Enable/disable a user account."""
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash('Cannot deactivate your own account.', 'warning')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        state = 'activated' if user.is_active else 'deactivated'
        flash(f'User "{user.username}" {state}.', 'success')
    return redirect(url_for('settings.index'))


@settings_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_password(user_id):
    """Reset a user's password."""
    user = db.get_or_404(User, user_id)
    new_pw = request.form.get('new_password', '')
    if len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('settings.index'))
    user.set_password(new_pw)
    db.session.commit()
    flash(f'Password reset for "{user.username}".', 'success')
    return redirect(url_for('settings.index'))


# ---------------------------------------------------------------------------
# Plan Master
# ---------------------------------------------------------------------------

@settings_bp.route('/plans', methods=['GET', 'POST'])
@login_required
@admin_required
def plans():
    """Manage rental plan master data."""
    if request.method == 'POST':
        try:
            plan = Plan(
                plan_name=request.form['plan_name'].strip(),
                validity_in_days=int(request.form['validity_in_days']),
                cost=float(request.form['cost']),
                is_active=True,
            )
            db.session.add(plan)
            db.session.commit()
            log_activity(current_user.username, 'Add', 'Plan', plan.plan_id,
                         f'Added plan: {plan.plan_name}', request.remote_addr)
            flash(f'Plan "{plan.plan_name}" created.', 'success')
            return redirect(url_for('settings.plans'))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding plan: {exc}', exc_info=True)
            flash(f'Error adding plan: {exc}', 'danger')

    all_plans = Plan.query.order_by(Plan.is_active.desc(), Plan.validity_in_days.asc()).all()
    return render_template('settings/plans.html', plans=all_plans, active_page='settings_plans')


@settings_bp.route('/plans/<int:plan_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_plan(plan_id):
    """Update a rental plan."""
    plan = db.get_or_404(Plan, plan_id)
    try:
        plan.plan_name = request.form['plan_name'].strip()
        plan.validity_in_days = int(request.form['validity_in_days'])
        plan.cost = float(request.form['cost'])
        db.session.commit()
        log_activity(current_user.username, 'Edit', 'Plan', plan.plan_id,
                     f'Edited plan: {plan.plan_name}', request.remote_addr)
        flash('Plan updated.', 'success')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f'Error editing plan {plan_id}: {exc}', exc_info=True)
        flash(f'Error updating plan: {exc}', 'danger')
    return redirect(url_for('settings.plans'))


@settings_bp.route('/plans/<int:plan_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_plan(plan_id):
    """Activate or deactivate a rental plan."""
    plan = db.get_or_404(Plan, plan_id)
    plan.is_active = not plan.is_active
    db.session.commit()
    flash(f'Plan "{plan.plan_name}" {"activated" if plan.is_active else "deactivated"}.', 'success')
    return redirect(url_for('settings.plans'))


# ---------------------------------------------------------------------------
# Database Console
# ---------------------------------------------------------------------------

@settings_bp.route('/database', methods=['GET', 'POST'])
@login_required
@admin_required
def database():
    """Run admin-approved SQL against existing application tables."""
    sql = request.form.get('sql', '').strip()
    result = None
    error = None
    tables = _schema_snapshot()

    if request.method == 'POST':
        target_table = None
        try:
            statement, operation = _normalise_sql(sql)
            sql = statement

            if operation != 'select':
                if request.form.get('confirm_write') != 'on':
                    raise ValueError('Confirm database writes before running INSERT, UPDATE, or DELETE.')
                target_table = _validate_write_table(
                    operation,
                    statement,
                    {table['name'] for table in tables},
                )

            result = _run_database_statement(statement, operation)

            if operation != 'select':
                log_activity(
                    current_user.username,
                    operation.upper(),
                    'Database',
                    remarks=(
                        f'{operation.upper()} on {target_table}; '
                        f'rows affected: {result["rows_affected"]}; '
                        f'SQL: {statement[:500]}'
                    ),
                    ip_address=request.remote_addr,
                )
                flash(f'{operation.upper()} completed. Rows affected: {result["rows_affected"]}.', 'success')

            tables = _schema_snapshot()
        except (ValueError, SQLAlchemyError) as exc:
            db.session.rollback()
            error = str(getattr(exc, 'orig', exc))
            current_app.logger.warning(f'Database console error: {error}')

    return render_template(
        'settings/database.html',
        active_page='settings_database',
        tables=tables,
        sql=sql,
        result=result,
        error=error,
    )


# ---------------------------------------------------------------------------
# Backup / Restore
# ---------------------------------------------------------------------------

@settings_bp.route('/backup', methods=['POST'])
@login_required
@admin_required
def backup():
    """Create a manual database backup."""
    try:
        path = create_backup()
        log_activity(current_user.username, 'Backup', 'System',
                     remarks=f'Manual backup: {os.path.basename(path)}', ip_address=request.remote_addr)
        flash(f'Backup created: {os.path.basename(path)}', 'success')
    except Exception as exc:
        current_app.logger.error(f'Backup error: {exc}', exc_info=True)
        flash(f'Backup failed: {exc}', 'danger')
    return redirect(url_for('settings.index'))


@settings_bp.route('/backup/download/<filename>')
@login_required
@admin_required
def download_backup(filename):
    """Download a specific backup file."""
    backup_dir = current_app.config['BACKUP_FOLDER']
    path = os.path.join(backup_dir, filename)
    if not os.path.exists(path):
        flash('Backup file not found.', 'danger')
        return redirect(url_for('settings.index'))
    return send_file(path, as_attachment=True)


@settings_bp.route('/restore', methods=['POST'])
@login_required
@admin_required
def restore():
    """Restore database from uploaded .db file."""
    db_file = request.files.get('db_file')
    if not db_file or not db_file.filename.endswith('.db'):
        flash('Please upload a valid .db backup file.', 'danger')
        return redirect(url_for('settings.index'))

    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        db_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        restore_backup(tmp_path)
        log_activity(current_user.username, 'Restore', 'System',
                     remarks='Database restored from uploaded backup', ip_address=request.remote_addr)
        flash('Database restored successfully! Restart the application if needed.', 'success')
    except Exception as exc:
        current_app.logger.error(f'Restore error: {exc}', exc_info=True)
        flash(f'Restore failed: {exc}', 'danger')
    finally:
        os.unlink(tmp_path)

    return redirect(url_for('settings.index'))


# ---------------------------------------------------------------------------
# Cron-safe backup endpoint (protected by token)
# ---------------------------------------------------------------------------

@settings_bp.route('/api/backup-cron')
def cron_backup():
    """
    HTTP-triggered backup for external cron services (e.g., cron-job.org).
    Protected by secret token in query param: ?token=<BACKUP_TOKEN>
    """
    token = request.args.get('token', '')
    if token != current_app.config.get('BACKUP_TOKEN', ''):
        return 'Unauthorized', 401
    try:
        path = create_backup()
        return f'Backup created: {os.path.basename(path)}', 200
    except Exception as exc:
        current_app.logger.error(f'Cron backup error: {exc}', exc_info=True)
        return f'Backup failed: {exc}', 500
