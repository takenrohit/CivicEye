from civiceye.extensions import db
from civiceye.models import Complaint, Notification

from .conftest import login, logout, submit


def _make_complaint(client, user):
    login(client, user.email)
    submit(client)
    logout(client)
    return Complaint.query.order_by(Complaint.id.desc()).first()


def test_anonymous_cannot_submit_or_view(client, citizen):
    c = _make_complaint(client, citizen)
    assert client.get("/me/complaints/new").status_code == 302
    assert client.post("/me/complaints/new").status_code in (302, 401)
    assert client.get(f"/me/complaints/{c.public_id}").status_code == 302
    att = c.attachments[0].public_id
    assert client.get(f"/media/{att}").status_code == 302
    assert client.get("/staff/").status_code == 302
    assert client.get("/api/nearby?lat=12.9&lon=77.5").status_code in (302, 401)


def test_other_citizen_cannot_access_private_records(client, citizen, citizen2):
    c = _make_complaint(client, citizen)
    login(client, citizen2.email)
    assert client.get(f"/me/complaints/{c.public_id}").status_code == 404
    assert client.get(f"/media/{c.attachments[0].public_id}").status_code == 404
    assert client.post(f"/me/complaints/{c.public_id}/category", data={"category": "other"}).status_code == 404
    assert client.post(f"/me/complaints/{c.public_id}/reopen", data={"reason": "x" * 20}).status_code == 404
    assert client.get("/me/complaints").data.count(c.public_id.encode()) == 0
    assert client.get("/staff/").status_code == 403
    assert client.get(f"/staff/complaints/{c.public_id}").status_code == 403
    assert client.get("/staff/complaints/export.csv").status_code == 403


def test_owner_can_view_own(client, citizen):
    c = _make_complaint(client, citizen)
    login(client, citizen.email)
    assert client.get(f"/me/complaints/{c.public_id}").status_code == 200
    r = client.get(f"/media/{c.attachments[0].public_id}")
    assert r.status_code == 200 and r.mimetype == "image/jpeg"
    assert "no-store" in r.headers["Cache-Control"]


def test_citizen_cannot_change_status(client, citizen):
    c = _make_complaint(client, citizen)
    login(client, citizen.email)
    r = client.post(f"/staff/complaints/{c.public_id}/status", data={"status": "resolved", "public_note": "done"})
    assert r.status_code == 403
    assert db.session.get(Complaint, c.id).status == "submitted"


def test_reviewer_access_and_admin_only_pages(client, citizen, reviewer, admin):
    c = _make_complaint(client, citizen)
    login(client, reviewer.email)
    assert client.get(f"/staff/complaints/{c.public_id}").status_code == 200
    assert client.get(f"/media/{c.attachments[0].public_id}").status_code == 200
    assert client.get("/staff/admin/users").status_code == 403
    assert client.get("/staff/admin/audit").status_code == 403
    logout(client)
    login(client, admin.email)
    assert client.get("/staff/admin/users").status_code == 200
    assert client.get("/staff/admin/audit").status_code == 200


def test_reviewer_cannot_act_on_other_reviewers_assignment(client, app, citizen, reviewer, admin):
    from civiceye.models import Role
    from .conftest import make_user
    other = make_user("rev2@example.com", Role.REVIEWER)
    c = _make_complaint(client, citizen)
    c.assigned_to_id = other.id
    from civiceye.extensions import db
    db.session.commit()
    login(client, reviewer.email)
    r = client.post(f"/staff/complaints/{c.public_id}/status", data={"status": "under_review"})
    assert r.status_code == 403


def test_notifications_are_private(client, citizen, citizen2):
    _make_complaint(client, citizen)
    login(client, citizen2.email)
    page = client.get("/me/notifications")
    assert page.status_code == 200
    n = Notification.query.filter_by(user_id=citizen.id).first()
    assert n.message.encode() not in page.data


def test_referrer_policy_allows_map_tiles(client):
    # OSM tile servers block requests without a Referer; only the origin is sent cross-site.
    assert client.get("/").headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_public_pages(client):
    for url in ("/", "/guidance", "/privacy", "/login", "/register"):
        r = client.get(url)
        assert r.status_code == 200
        assert b"Not an emergency service" in r.data or b"not an emergency service" in r.data
