from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.auth import bp
from app.auth.forms import LoginForm, RegistrationForm
from app.models import User


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    # Redirect if already logged in
    if current_user.is_authenticated:
        if current_user.is_therapist():
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('patient.dashboard'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()

        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('auth.login'))

        login_user(user, remember=form.remember_me.data)
        flash(f'Welcome back, {user.full_name}!', 'success')

        # Redirect to appropriate dashboard
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)

        if user.is_therapist():
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('patient.dashboard'))

    return render_template('auth/login.html', title='Sign In', form=form)


@bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle patient registration."""
    if current_user.is_authenticated:
        return redirect(url_for('patient.dashboard'))

    form = RegistrationForm()

    if form.validate_on_submit():
        user = User(
            email=form.email.data.lower(),
            full_name=form.full_name.data,
            phone=form.phone.data or None,
            role='patient'
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.commit()

        flash('Your account has been created! You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', title='Register', form=form)


@bp.route('/logout')
@login_required
def logout():
    """Handle user logout."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))