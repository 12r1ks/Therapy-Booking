
from datetime import datetime, date, time
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager

class User(UserMixin, db.Model):
    """User model for both patients and therapist."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='patient')  # 'patient' or 'therapist'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic',
                                   foreign_keys='Appointment.patient_id')

    def set_password(self, password):
        """Hash and set the password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if provided password matches hash."""
        return check_password_hash(self.password_hash, password)

    def is_therapist(self):
        """Check if user is a therapist."""
        return self.role == 'therapist'

    def __repr__(self):
        return f'<User {self.email}>'


@login_manager.user_loader
def load_user(id):
    """Flask-Login user loader callback."""
    return User.query.get(int(id))


class Appointment(db.Model):
    """Appointment model."""
    __tablename__ = 'appointments'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='scheduled')  # 'scheduled', 'cancelled', 'completed'
    cancellation_reason = db.Column(db.Text, nullable=True)
    cancelled_by = db.Column(db.String(20), nullable=True)  # 'therapist' or 'patient'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def can_cancel(self):
        """Check if appointment can be cancelled."""
        return self.status == 'scheduled' and self.start_time > datetime.utcnow()

    def can_reschedule(self):
        """Check if appointment can be rescheduled (must be ≥2 days before)."""
        if self.status != 'scheduled':
            return False
        days_until = (self.start_time.date() - date.today()).days
        return days_until >= 2

    def __repr__(self):
        return f'<Appointment {self.id} - {self.start_time}>'


class AvailabilityBlock(db.Model):
    """Weekly recurring availability pattern."""
    __tablename__ = 'availability_blocks'

    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('day_of_week', 'start_time', 'end_time', name='unique_availability'),
    )

    @staticmethod
    def get_day_name(day_num):
        """Convert day number to name."""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return days[day_num]

    def __repr__(self):
        return f'<Availability {self.get_day_name(self.day_of_week)} {self.start_time}-{self.end_time}>'


class BlockedSlot(db.Model):
    """Specific blocked dates/times (vacation, meetings, etc.)."""
    __tablename__ = 'blocked_slots'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    reason = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<BlockedSlot {self.date} {self.start_time}-{self.end_time}>'
