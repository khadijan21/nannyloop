# backend/models.py
from datetime import datetime, timedelta
import secrets

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Household(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default="My Household")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    users = db.relationship("User", backref="household", lazy=True)
    children = db.relationship("Child", backref="household", lazy=True)
    invites = db.relationship("InviteCode", backref="household", lazy=True)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # "parent" or "carer"
    role = db.Column(db.String(20), nullable=False)

    household_id = db.Column(db.Integer, db.ForeignKey("household.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Child(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("household.id"), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.String(50), nullable=False)

    log_entries = db.relationship("LogEntry", backref="child", lazy=True)


class LogEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("household.id"), nullable=False)

    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False)
    carer_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text, nullable=False)

    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class InviteCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)

    household_id = db.Column(db.Integer, db.ForeignKey("household.id"), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)

    used_by_user_id = db.Column(db.Integer, nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def create(household_id: int, created_by_user_id: int, hours: int | None = None):
        code = secrets.token_urlsafe(8)
        invite = InviteCode(
            code=code,
            household_id=household_id,
            created_by_user_id=created_by_user_id,
        )
        if hours:
            invite.expires_at = datetime.utcnow() + timedelta(hours=hours)
        return invite

    def is_valid(self) -> bool:
        if self.used_at is not None:
            return False
        if self.expires_at is not None and datetime.utcnow() > self.expires_at:
            return False
        return True
