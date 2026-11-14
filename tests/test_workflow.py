import pytest

from civiceye.extensions import db
from civiceye.models import Attachment, Complaint, Department, ReopenRequest, StatusEvent
from civiceye.services.workflow import TRANSITIONS, WorkflowError, change_status

from .conftest import image_bytes, login, logout, submit


def _setup(client, citizen):
    login(client, citizen.email)
    submit(client)
    logout(client)
    return Complaint.query.one()


def _status(client, c, status, **kw):
    return client.post(f"/staff/complaints/{c.public_id}/status", data={"status": status, **kw},
                       content_type="multipart/form-data")


def test_transition_table_never_allows_direct_reopen():
    for src, targets in TRANSITIONS.items():
        assert "reopened" not in targets
        assert "submitted" not in targets


def test_full_lifecycle_and_reopen(client, citizen, reviewer):
    c = _setup(client, citizen)
    login(client, reviewer.email)
    _status(client, c, "under_review")
    # Assigned requires a department
    _status(client, c, "assigned")
    assert Complaint.query.one().status == "under_review"
    dep = Department.query.first()
    client.post(f"/staff/complaints/{c.public_id}/assign", data={"department_id": dep.id})
    _status(client, c, "assigned")
    _status(client, c, "in_progress")
    # Resolution requires a note
    _status(client, c, "resolved")
    assert Complaint.query.one().status == "in_progress"
    _status(client, c, "resolved", public_note="Filled by contractor (simulated).",
            resolution_image=(image_bytes(), "after.jpg"))
    c = Complaint.query.one()
    assert c.status == "resolved" and c.resolution_note and c.resolved_at
    assert Attachment.query.filter_by(kind="resolution").count() == 1
    events = StatusEvent.query.filter_by(event_type="status").order_by(StatusEvent.id).all()
    assert [(e.from_status, e.to_status) for e in events] == [
        (None, "submitted"), ("submitted", "under_review"), ("under_review", "assigned"),
        ("assigned", "in_progress"), ("in_progress", "resolved")]
    assert all(e.actor_id for e in events)

    # Staff cannot force reopen directly
    _status(client, c, "reopened")
    assert Complaint.query.one().status == "resolved"
    logout(client)

    login(client, citizen.email)
    r = client.post(f"/me/complaints/{c.public_id}/reopen", data={"reason": "Pothole is back after the rain."})
    assert r.status_code == 302
    assert Complaint.query.one().status == "resolved"  # unchanged until reviewed
    # duplicate pending requests are refused
    client.post(f"/me/complaints/{c.public_id}/reopen", data={"reason": "Pothole is back after the rain."})
    assert ReopenRequest.query.count() == 1
    logout(client)

    login(client, reviewer.email)
    req = ReopenRequest.query.one()
    client.post(f"/staff/reopen-requests/{req.id}", data={"decision": "approve", "note": "Confirmed"})
    c = Complaint.query.one()
    assert c.status == "reopened" and c.resolved_at is None
    assert ReopenRequest.query.one().state == "approved"
    _status(client, c, "under_review")
    assert Complaint.query.one().status == "under_review"


def test_rejection_requires_reason(client, citizen, reviewer):
    c = _setup(client, citizen)
    login(client, reviewer.email)
    _status(client, c, "rejected")
    assert Complaint.query.one().status == "submitted"
    _status(client, c, "rejected", public_note="Outside pilot area")
    assert Complaint.query.one().status == "rejected"
    _status(client, c, "under_review")
    assert Complaint.query.one().status == "rejected"  # terminal


def test_invalid_transition_rejected(app, citizen, reviewer, client):
    c = _setup(client, citizen)
    with pytest.raises(WorkflowError):
        change_status(c, "resolved", reviewer, public_note="x")
    with pytest.raises(WorkflowError):
        change_status(c, "under_review", citizen)


def test_decline_reopen_requires_reason(client, citizen, reviewer):
    c = _setup(client, citizen)
    c.status = "resolved"
    c.resolution_note = "done"
    db.session.commit()
    login(client, citizen.email)
    client.post(f"/me/complaints/{c.public_id}/reopen", data={"reason": "Still broken, see the corner."})
    logout(client)
    login(client, reviewer.email)
    req = ReopenRequest.query.one()
    client.post(f"/staff/reopen-requests/{req.id}", data={"decision": "decline", "note": ""})
    assert ReopenRequest.query.one().state == "pending"
    client.post(f"/staff/reopen-requests/{req.id}", data={"decision": "decline", "note": "Photo shows repaired surface"})
    assert ReopenRequest.query.one().state == "declined"
    assert Complaint.query.one().status == "resolved"


def test_internal_notes_hidden_from_citizen(client, citizen, reviewer):
    c = _setup(client, citizen)
    login(client, reviewer.email)
    client.post(f"/staff/complaints/{c.public_id}/note", data={"note": "SECRET-INTERNAL", "visibility": "internal"})
    client.post(f"/staff/complaints/{c.public_id}/note", data={"note": "PUBLIC-UPDATE", "visibility": "public"})
    _status(client, c, "under_review", internal_note="ALSO-SECRET")
    logout(client)
    login(client, citizen.email)
    page = client.get(f"/me/complaints/{c.public_id}").data
    assert b"PUBLIC-UPDATE" in page
    assert b"SECRET-INTERNAL" not in page and b"ALSO-SECRET" not in page
    assert reviewer.display_name.encode() not in page


def test_category_review_keeps_original(client, citizen, reviewer):
    c = _setup(client, citizen)
    login(client, reviewer.email)
    client.post(f"/staff/complaints/{c.public_id}/category", data={"category": "waterlogging"})
    c = Complaint.query.one()
    assert c.submitted_category == "pothole" and c.reviewed_category == "waterlogging"
    ev = StatusEvent.query.filter_by(event_type="category").one()
    assert ev.details["from"] is None and ev.details["to"] == "waterlogging"
