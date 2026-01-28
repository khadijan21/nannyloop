# backend/models.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Child(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.String(50), nullable=False)

    log_entries = db.relationship("LogEntry", backref="child", lazy=True)


class Carer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)


class LogEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False)
    carer_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
