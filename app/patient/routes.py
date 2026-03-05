from datetime import datetime, date, time, timedelta
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.patient import bp
from app.models import Appointment, AvailabilityBlock, BlockedSlot
from app.decorators import patient_required


@bp.route('/dashboard')
@login_required
@patient_required
def dashboard():
    """Patient dashboard showing upcoming and past appointments."""
    now = datetime.utcnow()

    # Get upcoming appointments
    upcoming = Appointment.query.filter(
        Appointment.patient_id == current_user.id,
        Appointment.start_time > now,
        Appointment.status == 'scheduled'
    ).order_by(Appointment.start_time.asc()).all()

    # Get past appointments (last 30 days)
    past_date = now - timedelta(days=30)
    past = Appointment.query.filter(
        Appointment.patient_id == current_user.id,
        Appointment.start_time <= now,
        Appointment.start_time >= past_date
    ).order_by(Appointment.start_time.desc()).limit(10).all()

    return render_template('patient/dashboard.html',
                           upcoming=upcoming,
                           past=past,
                           now=now)


@bp.route('/book', methods=['GET', 'POST'])
@login_required
@patient_required
def book():
    """Book a new appointment."""
    if request.method == 'POST':
        # Get selected date and time from form
        selected_date = request.form.get('date')
        selected_time = request.form.get('time')

        if not selected_date or not selected_time:
            flash('Please select both date and time.', 'error')
            return redirect(url_for('patient.book'))

        # Parse date and time
        appointment_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        appointment_time = datetime.strptime(selected_time, '%H:%M').time()

        # Create datetime objects
        start_datetime = datetime.combine(appointment_date, appointment_time)
        end_datetime = start_datetime + timedelta(hours=1)

        # Check if slot is still available
        existing = Appointment.query.filter(
            Appointment.start_time == start_datetime,
            Appointment.status == 'scheduled'
        ).first()

        if existing:
            flash('This slot is no longer available. Please choose another.', 'error')
            return redirect(url_for('patient.book'))

        # Create appointment
        appointment = Appointment(
            patient_id=current_user.id,
            start_time=start_datetime,
            end_time=end_datetime,
            status='scheduled'
        )
        db.session.add(appointment)
        db.session.commit()

        flash('Appointment booked successfully!', 'success')
        return redirect(url_for('patient.dashboard'))

    # GET request - show booking page
    # Get the next 30 days for the date picker
    today = date.today()
    available_dates = []

    for i in range(1, 31):  # Next 30 days
        check_date = today + timedelta(days=i)
        day_of_week = check_date.weekday()  # 0=Monday

        # Check if this day has availability
        availability = AvailabilityBlock.query.filter_by(
            day_of_week=day_of_week,
            is_available=True
        ).first()

        if availability:
            available_dates.append(check_date)

    return render_template('patient/book.html', available_dates=available_dates)


@bp.route('/book/slots/<date_str>')
@login_required
@patient_required
def get_slots(date_str):
    """HTMX endpoint: Get available slots for a specific date."""
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return '<p class="text-red-500">Invalid date format.</p>'

    slots = get_available_slots(selected_date)

    return render_template('patient/partials/time_slots.html',
                           slots=slots,
                           selected_date=selected_date)


def get_available_slots(selected_date):
    """
    Calculate available time slots for a given date.

    Algorithm:
    1. Get weekly availability for that day of week
    2. Generate hourly slots from availability
    3. Remove blocked slots for that specific date
    4. Remove already booked appointments
    5. Return available slots
    """
    day_of_week = selected_date.weekday()  # 0=Monday

    # 1. Get availability for this day
    availability = AvailabilityBlock.query.filter_by(
        day_of_week=day_of_week,
        is_available=True
    ).first()

    if not availability:
        return []

    # 2. Generate hourly slots
    slots = []
    current_time = datetime.combine(selected_date, availability.start_time)
    end_time = datetime.combine(selected_date, availability.end_time)

    while current_time < end_time:
        slots.append({
            'time': current_time.time(),
            'datetime': current_time,
            'display': current_time.strftime('%I:%M %p')
        })
        current_time += timedelta(hours=1)

    # 3. Remove blocked slots
    blocked = BlockedSlot.query.filter_by(date=selected_date).all()
    for block in blocked:
        slots = [s for s in slots
                 if not (s['time'] >= block.start_time and s['time'] < block.end_time)]

    # 4. Remove booked appointments
    start_of_day = datetime.combine(selected_date, time(0, 0))
    end_of_day = datetime.combine(selected_date, time(23, 59))

    appointments = Appointment.query.filter(
        Appointment.start_time >= start_of_day,
        Appointment.start_time <= end_of_day,
        Appointment.status == 'scheduled'
    ).all()

    booked_times = {a.start_time for a in appointments}
    slots = [s for s in slots if s['datetime'] not in booked_times]

    return slots


@bp.route('/appointments')
@login_required
@patient_required
def appointments():
    """View all patient appointments."""
    all_appointments = Appointment.query.filter_by(
        patient_id=current_user.id
    ).order_by(Appointment.start_time.desc()).all()

    return render_template('patient/appointments.html',
                           appointments=all_appointments,
                           now=datetime.utcnow())


@bp.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@login_required
@patient_required
def cancel_appointment(appointment_id):
    """Cancel an appointment."""
    appointment = Appointment.query.get_or_404(appointment_id)

    # Verify ownership
    if appointment.patient_id != current_user.id:
        flash('You cannot cancel this appointment.', 'error')
        return redirect(url_for('patient.appointments'))

    # Check if can cancel
    if not appointment.can_cancel():
        flash('This appointment cannot be cancelled.', 'error')
        return redirect(url_for('patient.appointments'))

    # Cancel the appointment
    appointment.status = 'cancelled'
    appointment.cancelled_by = 'patient'
    db.session.commit()

    flash('Appointment cancelled successfully.', 'success')
    return redirect(url_for('patient.appointments'))


@bp.route('/appointments/<int:appointment_id>/reschedule', methods=['GET', 'POST'])
@login_required
@patient_required
def reschedule_appointment(appointment_id):
    """Reschedule an appointment (only if ≥2 days before)."""
    appointment = Appointment.query.get_or_404(appointment_id)

    # Verify ownership
    if appointment.patient_id != current_user.id:
        flash('You cannot reschedule this appointment.', 'error')
        return redirect(url_for('patient.appointments'))

    # Check 2-day rule
    if not appointment.can_reschedule():
        flash('Appointments can only be rescheduled at least 2 days in advance.', 'error')
        return redirect(url_for('patient.appointments'))

    if request.method == 'POST':
        selected_date = request.form.get('date')
        selected_time = request.form.get('time')

        if not selected_date or not selected_time:
            flash('Please select both date and time.', 'error')
            return redirect(url_for('patient.reschedule_appointment',
                                   appointment_id=appointment_id))

        # Parse and create new datetime
        new_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        new_time = datetime.strptime(selected_time, '%H:%M').time()
        new_start = datetime.combine(new_date, new_time)
        new_end = new_start + timedelta(hours=1)

        # Check availability
        existing = Appointment.query.filter(
            Appointment.start_time == new_start,
            Appointment.status == 'scheduled',
            Appointment.id != appointment_id
        ).first()

        if existing:
            flash('This slot is no longer available.', 'error')
            return redirect(url_for('patient.reschedule_appointment',
                                   appointment_id=appointment_id))

        # Update appointment
        appointment.start_time = new_start
        appointment.end_time = new_end
        db.session.commit()

        flash('Appointment rescheduled successfully!', 'success')
        return redirect(url_for('patient.dashboard'))

    # GET - show reschedule form
    today = date.today()
    available_dates = []

    for i in range(2, 31):  # Start from 2 days ahead
        check_date = today + timedelta(days=i)
        day_of_week = check_date.weekday()

        availability = AvailabilityBlock.query.filter_by(
            day_of_week=day_of_week,
            is_available=True
        ).first()

        if availability:
            available_dates.append(check_date)

    return render_template('patient/reschedule.html',
                           appointment=appointment,
                           available_dates=available_dates)
