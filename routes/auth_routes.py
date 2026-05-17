"""
routes/auth_routes.py - Login, logout, and session management.
"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models.user import User
from utils.helpers import log_activity

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(email=email).first()

        if user and user.is_active and user.check_password(password):
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()

            log_activity(
                user_name=user.username,
                action_type='Login',
                module_name='Auth',
                remarks=f'Login from {request.remote_addr}',
                ip_address=request.remote_addr,
            )

            next_page = request.args.get('next')
            flash(f'Welcome back, {user.full_name or user.username}!', 'success')
            return redirect(next_page or url_for('dashboard.index'))

        flash('Invalid email or password. Please try again.', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Log user out."""
    log_activity(
        user_name=current_user.username,
        action_type='Logout',
        module_name='Auth',
        ip_address=request.remote_addr,
    )
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """
    One-time admin setup route.
    Disabled once a user exists or .setup_complete file is present.
    """
    import os
    flag_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.setup_complete')

    if os.path.exists(flag_file) or User.query.count() > 0:
        flash('Setup has already been completed.', 'warning')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()

        if not all([username, email, password]):
            flash('All fields are required.', 'danger')
            return render_template('setup.html')

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role='admin',
            is_active=True,
        )
        user.set_password(password)

        try:
            db.session.add(user)
            db.session.commit()
            # Create flag file to disable this route
            open(flag_file, 'w').close()
            flash('Admin account created! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as exc:
            db.session.rollback()
            flash(f'Error creating admin: {exc}', 'danger')

    return render_template('setup.html')
