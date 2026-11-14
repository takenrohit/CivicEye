import csv
import io

import pytest

from civiceye.ai import text
from civiceye.ai.image import get_image_detector
from civiceye.services.exports import safe_cell, to_csv
from civiceye.services.geo import haversine_m
from civiceye.services.storage import UploadError, safe_path

from .conftest import login, logout, submit


def test_haversine_known_distance():
    # 0.001 deg latitude ≈ 111.2 m
    assert haversine_m(12.9, 77.5, 12.901, 77.5) == pytest.approx(111.2, abs=0.5)
    # 0.001 deg longitude at 12.9°N ≈ 108.4 m (not 111 m as degree-Euclidean would imply)
    assert haversine_m(12.9, 77.5, 12.9, 77.501) == pytest.approx(108.4, abs=0.5)


def test_text_baseline():
    assert text.suggest("Huge pothole on main road").category == "pothole"
    assert text.suggest("Nothing relevant here").category is None
    tie = text.suggest("pothole full of garbage")
    assert tie.category is None  # ambiguous → no suggestion rather than a guess


def test_image_detector_unavailable_by_default():
    d = get_image_detector({"IMAGE_MODEL_WEIGHTS": ""})
    assert not d.available
    res = d.predict(None)
    assert res.status == "unavailable" and res.detections == []
    d = get_image_detector({"IMAGE_MODEL_WEIGHTS": "does/not/exist.pt"})
    assert d.predict(None).status == "unavailable"


def test_safe_path_blocks_traversal(tmp_path):
    with pytest.raises(UploadError):
        safe_path(str(tmp_path), "../evil.txt")
    with pytest.raises(UploadError):
        safe_path(str(tmp_path), "sub/../../evil.txt")
    assert safe_path(str(tmp_path), "ok.png").parent == tmp_path.resolve()


def test_csv_formula_injection():
    assert safe_cell("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")"
    assert safe_cell("+1") == "'+1" and safe_cell("@SUM") == "'@SUM"
    assert safe_cell("normal") == "normal" and safe_cell(None) == ""
    rows = list(csv.reader(io.StringIO(to_csv(["a"], [["=1+1"]]))))
    assert rows[1][0] == "'=1+1"


def test_csv_export_authorized_and_safe(client, citizen, reviewer):
    login(client, citizen.email)
    submit(client, description="=cmd|' /C calc'!A0 pothole near the bus stop")
    logout(client)
    login(client, reviewer.email)
    r = client.get("/staff/complaints/export.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    rows = list(csv.reader(io.StringIO(r.data.decode())))
    assert rows[0][0] == "complaint_id"
    desc = rows[1][rows[0].index("description")]
    assert desc.startswith("'=")
    assert citizen.email not in r.data.decode()
    assert rows[1][rows[0].index("data_label")] == "REAL"


def test_dashboard_with_empty_data(client, reviewer):
    login(client, reviewer.email)
    r = client.get("/staff/")
    assert r.status_code == 200
    assert b"No resolved reports yet" in r.data
    assert client.get("/staff/map").status_code == 200
    assert client.get("/staff/complaints").status_code == 200


def test_dashboard_counts_reopened(client, app, citizen, reviewer):
    from civiceye.extensions import db
    from civiceye.models import Complaint
    login(client, citizen.email)
    submit(client)
    submit(client)
    logout(client)
    a, b = Complaint.query.all()
    a.status = "reopened"
    b.status = "resolved"
    b.resolved_at = b.created_at
    db.session.commit()
    login(client, reviewer.email)
    r = client.get("/staff/")
    assert b"n = 1 currently resolved" in r.data
    assert b"Reopened reports are counted as unresolved" in r.data


def test_seed_demo_labels_data(app):
    from civiceye.models import Complaint, InferenceRecord, User
    runner = app.test_cli_runner()
    res = runner.invoke(args=["seed-demo", "--count", "5", "--yes"])
    assert res.exit_code == 0, res.output
    assert Complaint.query.count() == 5
    assert all(c.is_demo for c in Complaint.query.all())
    assert all(u.is_demo for u in User.query.all())
    assert InferenceRecord.query.count() == 0  # no fake AI results seeded
    res = runner.invoke(args=["purge-demo", "--yes"])
    assert res.exit_code == 0, res.output
    assert Complaint.query.count() == 0


def test_purge_demo_keeps_real_data(client, app, citizen):
    from civiceye.models import Complaint
    login(client, citizen.email)
    submit(client)
    runner = app.test_cli_runner()
    runner.invoke(args=["seed-demo", "--count", "3", "--yes"])
    runner.invoke(args=["purge-demo", "--yes"])
    assert Complaint.query.count() == 1 and not Complaint.query.one().is_demo


def test_create_admin_command(app):
    from civiceye.models import User
    runner = app.test_cli_runner()
    res = runner.invoke(args=["create-admin", "--email", "boss@example.com", "--name", "Boss"],
                        input="admin-pass-123\nadmin-pass-123\n")
    assert res.exit_code == 0, res.output
    u = User.query.filter_by(email="boss@example.com").one()
    assert u.role == "admin" and u.check_password("admin-pass-123")
    res = runner.invoke(args=["create-admin", "--email", "weak@example.com", "--name", "W"], input="short\nshort\n")
    assert res.exit_code != 0
