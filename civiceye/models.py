"""Database models. All timestamps are stored as naive UTC and displayed in Asia/Kolkata."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion


def new_public_id() -> str:
    """Opaque, non-sequential complaint identifier (~60 bits of randomness)."""
    return "CE-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))


class Role:
    CITIZEN = "citizen"
    REVIEWER = "reviewer"
    ADMIN = "admin"
    ALL = (CITIZEN, REVIEWER, ADMIN)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=Role.CITIZEN, index=True)
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    department = db.relationship("Department")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)  # scrypt by default in Werkzeug 3

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:  # Flask-Login hook
        return self.is_active_account

    @property
    def is_staff(self) -> bool:
        return self.role in (Role.REVIEWER, Role.ADMIN)

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN


class Department(db.Model):
    """Simulated project departments unless genuine municipal participation is arranged."""
    __tablename__ = "departments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    is_simulated = db.Column(db.Boolean, nullable=False, default=True)


class CategoryDepartment(db.Model):
    __tablename__ = "category_departments"
    category = db.Column(db.String(30), primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    department = db.relationship("Department")


class Complaint(db.Model):
    __tablename__ = "complaints"
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(20), unique=True, nullable=False, index=True, default=new_public_id)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    description = db.Column(db.Text, nullable=False)
    landmark = db.Column(db.String(120))
    observed_at = db.Column(db.DateTime, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    location_source = db.Column(db.String(20), nullable=False, default="manual")  # geolocation|manual

    # Categories: AI suggestions live in InferenceRecord; these are human decisions.
    submitted_category = db.Column(db.String(30), nullable=False)
    reviewed_category = db.Column(db.String(30))

    status = db.Column(db.String(20), nullable=False, default="submitted", index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), index=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)

    # Priority inputs (None = unknown, distinct from a confirmed low value)
    reviewed_risk = db.Column(db.Integer)  # 1..5 human-reviewed safety risk
    location_sensitivity = db.Column(db.Integer)  # 0..2 reviewed context
    location_rationale = db.Column(db.String(255))
    priority_override = db.Column(db.Float)
    priority_override_reason = db.Column(db.String(255))

    resolution_note = db.Column(db.Text)
    resolved_at = db.Column(db.DateTime)

    consent_given_at = db.Column(db.DateTime, nullable=False)
    is_demo = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])
    department = db.relationship("Department")
    attachments = db.relationship("Attachment", back_populates="complaint", order_by="Attachment.id",
                                  cascade="all, delete-orphan")
    history = db.relationship("StatusEvent", back_populates="complaint", order_by="StatusEvent.created_at",
                              cascade="all, delete-orphan")
    inferences = db.relationship("InferenceRecord", back_populates="complaint", order_by="InferenceRecord.id",
                                 cascade="all, delete-orphan")

    @property
    def effective_category(self) -> str:
        return self.reviewed_category or self.submitted_category

    @property
    def primary_image(self):
        for a in self.attachments:
            if a.kind == "evidence":
                return a
        return None


class Attachment(db.Model):
    __tablename__ = "attachments"
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(32), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(16))
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=False, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="evidence")  # evidence|clarification|resolution
    stored_name = db.Column(db.String(80), nullable=False, unique=True)  # random name, never user-supplied
    mime_type = db.Column(db.String(40), nullable=False)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    size_bytes = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    complaint = db.relationship("Complaint", back_populates="attachments")


class InferenceRecord(db.Model):
    """Original AI/rule output, kept separate from human decisions."""
    __tablename__ = "inference_records"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)  # image|text
    method = db.Column(db.String(30), nullable=False)  # e.g. unavailable|rule_based_keywords|yolo
    model_id = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False)  # ok|unavailable|error
    output_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    complaint = db.relationship("Complaint", back_populates="inferences")


class StatusEvent(db.Model):
    """Audit trail of status changes and other complaint events."""
    __tablename__ = "status_events"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    event_type = db.Column(db.String(30), nullable=False, default="status")  # status|category|risk|assignment|note|priority_override|reopen_request
    from_status = db.Column(db.String(20))
    to_status = db.Column(db.String(20))
    public_note = db.Column(db.Text)  # visible to the citizen
    internal_note = db.Column(db.Text)  # staff only
    details = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    complaint = db.relationship("Complaint", back_populates="history")
    actor = db.relationship("User")


class Assignment(db.Model):
    __tablename__ = "assignments"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"))
    assignee_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ReopenRequest(db.Model):
    __tablename__ = "reopen_requests"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=False, index=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    state = db.Column(db.String(20), nullable=False, default="pending", index=True)  # pending|approved|declined
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    decision_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    decided_at = db.Column(db.DateTime)

    complaint = db.relationship("Complaint")
    requested_by = db.relationship("User", foreign_keys=[requested_by_id])


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"))
    message = db.Column(db.String(300), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    complaint = db.relationship("Complaint")


class Feedback(db.Model):
    __tablename__ = "feedback"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    rating = db.Column(db.Integer)  # 1..5 optional
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User")


class AuditEvent(db.Model):
    """System-level audit (logins, account changes, config changes, seeding)."""
    __tablename__ = "audit_events"
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(60), nullable=False, index=True)
    target = db.Column(db.String(120))
    details = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    actor = db.relationship("User")
