from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user


def therapist_required(f):
    """Decorator to require therapist role for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_therapist():
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('patient.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def patient_required(f):
    """Decorator to require patient role for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if current_user.is_therapist():
            flash('This page is for patients only.', 'info')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function
