import io

import pytest
from PIL import Image

from civiceye import create_app
from civiceye.cli import ensure_departments
from civiceye.config import TestConfig
from civiceye.extensions import db as _db
from civiceye.models import Role, User


@pytest.fixture()
def app(tmp_path):
    class Cfg(TestConfig):
        UPLOAD_DIR = str(tmp_path / "uploads")
    app = create_app(Cfg)
    with app.app_context():
        _db.create_all()
        ensure_departments()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(email, role=Role.CITIZEN, password="correct-horse-1"):
    u = User(email=email, display_name=email.split("@")[0], role=role)
    u.set_password(password)
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture()
def citizen(app):
    return make_user("alice@example.com")


@pytest.fixture()
def citizen2(app):
    return make_user("bob@example.com")


@pytest.fixture()
def reviewer(app):
    return make_user("zq.officer.x@example.com", Role.REVIEWER)


@pytest.fixture()
def admin(app):
    return make_user("admin@example.com", Role.ADMIN)


def login(client, email, password="correct-horse-1"):
    return client.post("/login", data={"email": email, "password": password})


def logout(client):
    return client.post("/logout")


def image_bytes(fmt="JPEG", size=(200, 150), exif_gps=False):
    img = Image.new("RGB", size, (120, 120, 120))
    buf = io.BytesIO()
    kwargs = {}
    if exif_gps:
        exif = Image.Exif()
        exif[0x010F] = "TestCam"  # Make
        exif[0x8825] = {2: (12.0, 54.0, 29.0)}  # GPSInfo latitude
        kwargs["exif"] = exif
    img.save(buf, format=fmt, **kwargs)
    buf.seek(0)
    return buf


def complaint_form(**over):
    data = {
        "description": "Big pothole near the bus stop, bikes swerving.",
        "observed_at": "2026-01-01T10:00",
        "latitude": "12.9081",
        "longitude": "77.5665",
        "location_source": "manual",
        "category": "pothole",
        "consent": "1",
        "image": (image_bytes(), "photo.jpg"),
    }
    data.update(over)
    return data


def submit(client, **over):
    """Submit a complaint; observation time defaults to 2 hours ago (IST) so it stays valid."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    over.setdefault("observed_at",
                    (datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"))
    return client.post("/me/complaints/new", data=complaint_form(**over), content_type="multipart/form-data")
