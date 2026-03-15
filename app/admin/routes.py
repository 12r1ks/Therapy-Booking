from datetime import datetime, date, time, timedelta
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.admin import bp
from app.models import User, Appointment, AvailabilityBlock, BlockedSlot
from app.decorators import therapist_required


@bp.route('/dashboard')
@therapist_required
def dashboard():
    """Therapist main dashboard with overview statistics."""
    today = date.today()
    now = datetime.utcnow()

    # Today's appointments
    start_of_today = datetime.combine(today, time(0, 0))
    end_of_today = datetime.combine(today, time(23, 59))

    todays_appointments = Appointment.query.filter(
        Appointment.start_time >= start_of_today,
        Appointment.start_time <= end_of_today,
        Appointment.status == 'scheduled'
    ).order_by(Appointment.start_time.asc()).all()

    # Upcoming appointments (next 7 days)
    next_week = now + timedelta(days=7)
    upcoming = Appointment.query.filter(
        Appointment.start_time > now,
        Appointment.start_time <= next_week,
        Appointment.status == 'scheduled'
    ).order_by(Appointment.start_time.asc()).all()

    # Recent activity (last 10 bookings/cancellations)
    recent = Appointment.query.order_by(
        Appointment.created_at.desc()
    ).limit(10).all()

    # Statistics
    stats = {
        'today_count': len(todays_appointments),
        'upcoming_count': len(upcoming),
        'total_patients': User.query.filter_by(role='patient').count(),
        'this_month': Appointment.query.filter(
            Appointment.start_time >= datetime(today.year, today.month, 1),
            Appointment.status == 'completed'
        ).count()
    }

    return render_template('admin/dashboard.html',
                           todays_appointments=todays_appointments,
                           upcoming=upcoming,
                           recent=recent,
                           stats=stats,
                           now=now)


@bp.route('/availability', methods=['GET', 'POST'])
@therapist_required
def availability():
    """Manage weekly availability schedule."""
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    if request.method == 'POST':
        # Clear existing availability
        AvailabilityBlock.query.delete()

        # Process each day
        for i, day in enumerate(days):
            is_available = request.form.get(f'available_{i}') == 'on'
            start_time = request.form.get(f'start_{i}')
            end_time = request.form.get(f'end_{i}')

            if is_available and start_time and end_time:
                block = AvailabilityBlock(
                    day_of_week=i,  # 0=Monday
                    start_time=datetime.strptime(start_time, '%H:%M').time(),
                    end_time=datetime.strptime(end_time, '%H:%M').time(),
                    is_available=True
                )
                db.session.add(block)

        db.session.commit()
        flash('Availability updated successfully!', 'success')
        return redirect(url_for('admin.availability'))

    # GET - load current availability
    current_availability = {}
    for block in AvailabilityBlock.query.all():
        current_availability[block.day_of_week] = block

    return render_template('admin/availability.html',
                           days=days,
                           current=current_availability)


@bp.route('/blocked-slots', methods=['GET', 'POST'])
@therapist_required
def blocked_slots():
    """Manage blocked time slots for specific dates."""
    if request.method == 'POST':
        date_str = request.form.get('date')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        reason = request.form.get('reason', '')

        if not all([date_str, start_time, end_time]):
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('admin.blocked_slots'))

        blocked = BlockedSlot(
            date=datetime.strptime(date_str, '%Y-%m-%d').date(),
            start_time=datetime.strptime(start_time, '%H:%M').time(),
            end_time=datetime.strptime(end_time, '%H:%M').time(),
            reason=reason
        )
        db.session.add(blocked)
        db.session.commit()

        flash('Time slot blocked successfully!', 'success')
        return redirect(url_for('admin.blocked_slots'))

    # GET - show blocked slots
    blocks = BlockedSlot.query.filter(
        BlockedSlot.date >= date.today()
    ).order_by(BlockedSlot.date.asc()).all()

    return render_template('admin/blocked_slots.html', blocks=blocks, now=datetime.utcnow())


@bp.route('/blocked-slots/<int:block_id>/delete', methods=['POST'])
@therapist_required
def delete_blocked_slot(block_id):
    """Delete a blocked time slot."""
    block = BlockedSlot.query.get_or_404(block_id)
    db.session.delete(block)
    db.session.commit()

    flash('Blocked slot removed.', 'success')
    return redirect(url_for('admin.blocked_slots'))


@bp.route('/appointments')
@therapist_required
def appointments():
    """View all appointments with filtering."""
    # Get filter parameters
    status = request.args.get('status', 'all')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search = request.args.get('search', '')

    # Base query
    query = Appointment.query.join(User)

    # Apply filters
    if status != 'all':
        query = query.filter(Appointment.status == status)

    if date_from:
        from_date = datetime.strptime(date_from, '%Y-%m-%d')
        query = query.filter(Appointment.start_time >= from_date)

    if date_to:
        to_date = datetime.strptime(date_to, '%Y-%m-%d')
        query = query.filter(Appointment.start_time <= to_date)

    if search:
        query = query.filter(User.full_name.ilike(f'%{search}%'))

    appointments = query.order_by(Appointment.start_time.asc()).all()

    return render_template('admin/appointments.html',
                           appointments=appointments,
                           filters={'status': status, 'date_from': date_from,
                                   'date_to': date_to, 'search': search})


@bp.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@therapist_required
def cancel_appointment(appointment_id):
    """Cancel an appointment (therapist action)."""
    appointment = Appointment.query.get_or_404(appointment_id)
    reason = request.form.get('reason', 'Cancelled by therapist')

    appointment.status = 'cancelled'
    appointment.cancelled_by = 'therapist'
    appointment.notes = reason
    db.session.commit()

    flash('Appointment cancelled.', 'success')
    return redirect(url_for('admin.appointments'))


@bp.route('/appointments/<int:appointment_id>/complete', methods=['POST'])
@therapist_required
def complete_appointment(appointment_id):
    """Mark an appointment as completed."""
    appointment = Appointment.query.get_or_404(appointment_id)
    appointment.status = 'completed'
    db.session.commit()

    flash('Appointment marked as completed.', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/patients')
@therapist_required
def patients():
    """View all registered patients."""
    search = request.args.get('search', '')

    query = User.query.filter_by(role='patient')

    if search:
        query = query.filter(User.full_name.ilike(f'%{search}%'))

    all_patients = query.order_by(User.created_at.desc()).all()

    return render_template('admin/patients.html',
                           patients=all_patients,
                           search=search)


@bp.route('/patients/<int:patient_id>')
@therapist_required
def patient_detail(patient_id):
    """View patient details and appointment history."""
    patient = User.query.get_or_404(patient_id)

    if patient.role != 'patient':
        flash('Invalid patient.', 'error')
        return redirect(url_for('admin.patients'))

    appointments = Appointment.query.filter_by(
        patient_id=patient_id
    ).order_by(Appointment.start_time.desc()).all()

    return render_template('admin/patient_detail.html',
                           patient=patient,
                           appointments=appointments)


@bp.route('/calendar')  
@therapist_required
def calendar():
    """Calendar view of all appointments."""
    # Get the month to display (default: current month)
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)

    # Get all appointments for the month
    start_of_month = datetime(year, month, 1)
    if month == 12:
        end_of_month = datetime(year + 1, 1, 1)
    else:
        end_of_month = datetime(year, month + 1, 1)

    appointments = Appointment.query.filter(
        Appointment.start_time >= start_of_month,
        Appointment.start_time < end_of_month
    ).all()

    # Organize by date string key for template access
    calendar_data = {}
    for apt in appointments:
        key = apt.start_time.strftime('%Y-%m-%d')
        if key not in calendar_data:
            calendar_data[key] = []
        calendar_data[key].append(apt)

    import calendar as cal
    month_days = cal.monthrange(year, month)[1]
    month_offset = cal.monthrange(year, month)[0]  # 0=Monday

    return render_template('admin/calendar.html',
                           year=year,
                           month=month,
                           month_days=month_days,
                           month_offset=month_offset,
                           calendar_data=calendar_data)
