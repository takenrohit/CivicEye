"""Regression tests for bugs found in the Phase 1 checkup."""
import json
import re

from civiceye.extensions import db
from civiceye.models import Attachment, Complaint, Department, User

from .conftest import image_bytes, login, logout, make_user, submit


def _demo_creds(output, role):
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == role:
            return parts[1], parts[2]
    raise AssertionError(output)


def test_purge_demo_after_demo_login_does_not_crash(app, client):
    runner = app.test_cli_runner()
    out = runner.invoke(args=["seed-demo", "--count", "3", "--yes"]).output
    email, pw = _demo_creds(out, "reviewer")
    assert login(client, email, pw).status_code == 302  # creates an audit event for the demo user
    res = runner.invoke(args=["purge-demo", "--yes"])
    assert res.exit_code == 0, res.output
    assert Complaint.query.count() == 0
    u = User.query.filter_by(email=email).one()
    assert not u.is_active_account  # kept for audit integrity, but cannot sign in
    logout(client)
    assert login(client, email, pw).status_code == 401


def test_seed_demo_rerun_regenerates_passwords(app, client):
    runner = app.test_cli_runner()
    _, pw1 = _demo_creds(runner.invoke(args=["seed-demo", "--count", "1", "--yes"]).output, "citizen")
    res = runner.invoke(args=["seed-demo", "--count", "1", "--yes"])
    assert res.exit_code == 0
    email, pw2 = _demo_creds(res.output, "citizen")
    assert pw1 != pw2
    assert login(client, email, pw2).status_code == 302


def test_seed_demo_never_touches_real_accounts(app):
    make_user("demo.citizen1@demo.civiceye.invalid")  # real (is_demo=False) account with that email
    res = app.test_cli_runner().invoke(args=["seed-demo", "--count", "1", "--yes"])
    assert res.exit_code != 0 and "not a demo account" in res.output


def test_nearby_api_separates_demo_and_excludes_rejected(app, client, citizen):
    app.test_cli_runner().invoke(args=["seed-demo", "--count", "30", "--yes"])
    login(client, citizen.email)
    c = Complaint.query.filter_by(is_demo=True).first()
    r = client.get(f"/api/nearby?lat={c.latitude}&lon={c.longitude}").get_json()
    assert r["results"] == []  # real user is not shown demo reports
    submit(client, latitude=str(c.latitude), longitude=str(c.longitude))
    mine = Complaint.query.filter_by(is_demo=False).one()
    assert len(client.get(f"/api/nearby?lat={c.latitude}&lon={c.longitude}").get_json()["results"]) == 1
    mine.status = "rejected"
    db.session.commit()
    assert client.get(f"/api/nearby?lat={c.latitude}&lon={c.longitude}").get_json()["results"] == []


def test_band_filter_applied_before_list_limit(app, client, citizen, reviewer, monkeypatch):
    import civiceye.blueprints.staff as staff
    monkeypatch.setattr(staff, "LIST_LIMIT", 2)
    login(client, citizen.email)
    for _ in range(3):
        submit(client)
    logout(client)
    oldest = Complaint.query.order_by(Complaint.id).first()  # newest-first list would cut this off
    oldest.reviewed_risk, oldest.location_sensitivity = 5, 2
    oldest.location_rationale = "test"
    oldest.priority_override = 0.9
    db.session.commit()
    login(client, reviewer.email)
    page = client.get("/staff/complaints?band=High").data
    assert oldest.public_id.encode() in page
    csv_rows = client.get("/staff/complaints/export.csv?band=High").data.decode().strip().splitlines()
    assert len(csv_rows) == 2  # header + the one High complaint


def test_clarification_photo_limit_independent_of_initial_photos(app, client, citizen):
    login(client, citizen.email)
    extras = [(image_bytes(), f"e{i}.jpg") for i in range(app.config["MAX_EXTRA_IMAGES"])]
    submit(client, extra_images=extras)
    c = Complaint.query.one()
    for i in range(app.config["MAX_CLARIFICATION_IMAGES"] + 1):
        client.post(f"/me/complaints/{c.public_id}/clarify", data={"note": f"n{i}", "image": (image_bytes(), "x.jpg")},
                    content_type="multipart/form-data")
    assert Attachment.query.filter_by(kind="clarification").count() == app.config["MAX_CLARIFICATION_IMAGES"]


def test_closed_complaint_cannot_be_reassigned(client, citizen, reviewer):
    login(client, citizen.email)
    submit(client)
    logout(client)
    c = Complaint.query.one()
    c.status = "rejected"
    db.session.commit()
    login(client, reviewer.email)
    client.post(f"/staff/complaints/{c.public_id}/assign", data={"department_id": Department.query.first().id})
    assert Complaint.query.one().department_id is None


def test_dashboard_chart_uses_readable_labels(client, citizen, reviewer):
    login(client, citizen.email)
    submit(client)
    logout(client)
    login(client, reviewer.email)
    html = client.get("/staff/").data.decode()
    data = json.loads(re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', html, re.S).group(1))
    assert data["cat_labels"] == ["Pothole / road damage"]
    assert data["status_labels"] == ["Submitted"]


def test_complaint_form_exposes_client_limits(client, citizen, app):
    login(client, citizen.email)
    html = client.get("/me/complaints/new").data.decode()
    assert f'data-max-image-bytes="{app.config["MAX_IMAGE_BYTES"]}"' in html
    assert f'data-max-extra="{app.config["MAX_EXTRA_IMAGES"]}"' in html
