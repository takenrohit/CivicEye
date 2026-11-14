from civiceye import create_app
from civiceye.config import TestConfig
from civiceye.extensions import db
from civiceye.models import User

from .conftest import login, logout


def test_register_login_logout(client):
    r = client.post("/register", data={"email": "New@Example.com", "display_name": "New User",
                                       "password": "longpassword9", "password2": "longpassword9",
                                       "accept_terms": "1"})
    assert r.status_code == 302
    u = User.query.filter_by(email="new@example.com").one()
    assert u.role == "citizen"
    assert u.password_hash != "longpassword9" and u.check_password("longpassword9")
    assert client.get("/me/").status_code == 200
    logout(client)
    assert client.get("/me/").status_code == 302  # redirected to login
    assert login(client, "new@example.com", "longpassword9").status_code == 302


def test_register_validation(client):
    r = client.post("/register", data={"email": "bad", "display_name": "x", "password": "short",
                                       "password2": "other"})
    assert r.status_code == 400
    assert User.query.count() == 0


def test_duplicate_email_rejected(client, citizen):
    r = client.post("/register", data={"email": citizen.email, "display_name": "Dup", "password": "longpassword9",
                                       "password2": "longpassword9", "accept_terms": "1"})
    assert r.status_code == 400


def test_wrong_password_generic_error(client, citizen):
    r = login(client, citizen.email, "wrong-password-1")
    assert r.status_code == 401
    assert b"Incorrect email or password" in r.data
    r = login(client, "nobody@example.com", "wrong-password-1")
    assert r.status_code == 401


def test_deactivated_user_cannot_login(client, citizen):
    citizen.is_active_account = False
    db.session.commit()
    assert login(client, citizen.email).status_code == 401


def test_open_redirect_blocked(client, citizen):
    r = client.post("/login?next=https://evil.example/", data={"email": citizen.email, "password": "correct-horse-1"})
    assert r.status_code == 302
    assert "evil.example" not in r.headers["Location"]


def test_csrf_enforced(tmp_path):
    class Cfg(TestConfig):
        WTF_CSRF_ENABLED = True
        UPLOAD_DIR = str(tmp_path)
    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        c = app.test_client()
        r = c.post("/register", data={"email": "a@b.co", "display_name": "AB", "password": "longpassword9",
                                      "password2": "longpassword9", "accept_terms": "1"})
        assert r.status_code == 400
        assert User.query.count() == 0
        db.drop_all()


def test_missing_secret_key_refuses_to_start(tmp_path):
    class Cfg(TestConfig):
        SECRET_KEY = None
        UPLOAD_DIR = str(tmp_path)
    try:
        create_app(Cfg)
    except RuntimeError as e:
        assert "SECRET_KEY" in str(e)
    else:
        raise AssertionError("app started without a secret key")
