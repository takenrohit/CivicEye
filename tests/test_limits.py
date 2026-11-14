import io
import os

import pytest
from PIL import Image

from civiceye import create_app
from civiceye.cli import ensure_departments
from civiceye.config import TestConfig
from civiceye.extensions import db
from civiceye.models import Attachment, Complaint

from .conftest import image_bytes, login, make_user, submit


def test_large_phone_photo_accepted_and_downscaled(client, citizen, app):
    # 12000x9000 (108 MP) is a real phone resolution; it must not be rejected.
    buf = io.BytesIO()
    Image.new("RGB", (12000, 9000), (90, 90, 90)).save(buf, "JPEG", quality=80)
    buf.seek(0)
    login(client, citizen.email)
    r = submit(client, image=(buf, "phone.jpg"))
    assert r.status_code == 302, r.data[:500]
    a = Attachment.query.one()
    assert max(a.width, a.height) == app.config["STORE_MAX_SIDE"]
    with Image.open(os.path.join(app.config["UPLOAD_DIR"], a.stored_name)) as im:
        assert max(im.size) == app.config["STORE_MAX_SIDE"]


def test_orientation_applied_before_downscale(client, citizen, app):
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° CW
    Image.new("RGB", (4000, 3000), (90, 90, 90)).save(buf, "JPEG", exif=exif)
    buf.seek(0)
    login(client, citizen.email)
    submit(client, image=(buf, "rotated.jpg"))
    a = Attachment.query.one()
    assert a.height > a.width  # portrait after applying EXIF orientation


def test_oversized_png_rejected(client, citizen):
    login(client, citizen.email)
    buf = io.BytesIO()
    Image.new("RGB", (8000, 7000)).save(buf, "PNG")  # 56 MP > PNG pixel limit
    buf.seek(0)
    r = submit(client, image=(buf, "huge.png"))
    assert r.status_code == 400 and b"PNG/WebP image is too large" in r.data


@pytest.fixture()
def limited_app(tmp_path):
    class Cfg(TestConfig):
        RATELIMIT_ENABLED = True
        UPLOAD_DIR = str(tmp_path)
        SUBMIT_RATE_LIMIT = "2 per hour"
        SUBMIT_ATTEMPT_RATE_LIMIT = "6 per hour"
    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        ensure_departments()
        yield app
        db.drop_all()


def test_failed_validation_does_not_use_up_submission_quota(limited_app):
    make_user("limit@example.com")
    c = limited_app.test_client()
    login(c, "limit@example.com")
    for _ in range(3):  # validation errors
        assert submit(c, consent="").status_code == 400
    assert submit(c).status_code == 302
    assert submit(c).status_code == 302
    assert submit(c).status_code == 429  # third accepted complaint within the hour
    assert Complaint.query.count() == 2


def test_attempt_limit_caps_repeated_failures(limited_app):
    make_user("spam@example.com")
    c = limited_app.test_client()
    login(c, "spam@example.com")
    codes = [submit(c, consent="").status_code for _ in range(7)]
    assert codes[:6] == [400] * 6 and codes[6] == 429


def test_login_rate_limited(limited_app):
    c = limited_app.test_client()
    codes = [c.post("/login", data={"email": "x@example.com", "password": "nope"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
