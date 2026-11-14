"""Complaint status workflow. Allowed transitions are defined and enforced here only."""
from __future__ import annotations

from ..extensions import db
from ..models import Complaint, Notification, StatusEvent, User, utcnow

STATUS_LABELS = {
    "submitted": "Submitted",
    "under_review": "Under Review",
    "assigned": "Assigned",
    "in_progress": "In Progress",
    "resolved": "Resolved",
    "rejected": "Rejected",
    "reopened": "Reopened",
}

# Staff-driven transitions. "reopened" is reached only through an approved
# reopening request (see approve_reopen), never set directly.
TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"under_review", "rejected"},
    "under_review": {"assigned", "rejected"},
    "assigned": {"in_progress", "under_review", "rejected"},
    "in_progress": {"resolved", "assigned"},
    "resolved": set(),
    "rejected": set(),
    "reopened": {"under_review", "assigned", "rejected"},
}

OPEN_STATUSES = {"submitted", "under_review", "assigned", "in_progress", "reopened"}


class WorkflowError(ValueError):
    pass


def allowed_next(status: str) -> list[str]:
    return sorted(TRANSITIONS.get(status, set()))


def notify(user_id: int, complaint: Complaint | None, message: str) -> None:
    db.session.add(Notification(user_id=user_id, complaint=complaint, message=message[:300]))


def change_status(complaint: Complaint, new_status: str, actor: User,
                  public_note: str = "", internal_note: str = "") -> StatusEvent:
    """Validate and apply a status change, recording a history event. Caller commits."""
    if not actor.is_staff:
        raise WorkflowError("Only reviewers or administrators can change complaint status.")
    old = complaint.status
    if new_status not in TRANSITIONS.get(old, set()):
        raise WorkflowError(f"Transition {STATUS_LABELS.get(old, old)} → "
                            f"{STATUS_LABELS.get(new_status, new_status)} is not allowed.")
    public_note = (public_note or "").strip()
    internal_note = (internal_note or "").strip()
    if new_status == "rejected" and not public_note:
        raise WorkflowError("A rejection requires a reason visible to the citizen.")
    if new_status == "assigned" and complaint.department_id is None:
        raise WorkflowError("Set a department (assignment) before moving to Assigned.")
    if new_status == "resolved":
        if not public_note:
            raise WorkflowError("Resolution requires a resolution note.")
        complaint.resolution_note = public_note
        complaint.resolved_at = utcnow()

    complaint.status = new_status
    event = StatusEvent(complaint=complaint, actor_id=actor.id, event_type="status",
                        from_status=old, to_status=new_status,
                        public_note=public_note or None, internal_note=internal_note or None)
    db.session.add(event)
    notify(complaint.reporter_id, complaint,
           f"Complaint {complaint.public_id} is now {STATUS_LABELS[new_status]}.")
    return event


def record_event(complaint: Complaint, actor: User | None, event_type: str, *,
                 public_note: str | None = None, internal_note: str | None = None,
                 details: dict | None = None) -> StatusEvent:
    event = StatusEvent(complaint=complaint, actor_id=actor.id if actor else None, event_type=event_type,
                        from_status=complaint.status, to_status=complaint.status,
                        public_note=public_note, internal_note=internal_note, details=details)
    db.session.add(event)
    return event


def approve_reopen(req, actor: User, note: str) -> None:
    """Approve a citizen reopening request: resolved → reopened."""
    if not actor.is_staff:
        raise WorkflowError("Only staff can decide reopening requests.")
    if req.state != "pending":
        raise WorkflowError("This request has already been decided.")
    c = req.complaint
    if c.status != "resolved":
        raise WorkflowError("Only resolved complaints can be reopened.")
    req.state = "approved"
    req.decided_by_id = actor.id
    req.decision_note = note or None
    req.decided_at = utcnow()
    old = c.status
    c.status = "reopened"
    c.resolved_at = None
    db.session.add(StatusEvent(complaint=c, actor_id=actor.id, event_type="status", from_status=old,
                               to_status="reopened", public_note=note or "Reopening request approved.",
                               details={"reopen_request_id": req.id}))
    notify(c.reporter_id, c, f"Your reopening request for {c.public_id} was approved.")


def decline_reopen(req, actor: User, note: str) -> None:
    if not actor.is_staff:
        raise WorkflowError("Only staff can decide reopening requests.")
    if req.state != "pending":
        raise WorkflowError("This request has already been decided.")
    if not (note or "").strip():
        raise WorkflowError("Declining a reopening request requires a reason.")
    req.state = "declined"
    req.decided_by_id = actor.id
    req.decision_note = note.strip()
    req.decided_at = utcnow()
    record_event(req.complaint, actor, "reopen_request", public_note=f"Reopening request declined: {note.strip()}")
    notify(req.complaint.reporter_id, req.complaint,
           f"Your reopening request for {req.complaint.public_id} was declined.")
