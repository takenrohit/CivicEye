"""CivicEye application factory."""
from __future__ import annotations

import logging
import os
from datetime import timezone
from zoneinfo import ZoneInfo

from flask import Flask, render_template
from flask_login import current_user

from .config import Config
from .extensions import csrf, db, limiter, login_manager, migrate


def create_app(config_object=None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("CIVICEYE_SECRET_KEY is not set. Copy .env.example to .env and set a random value.")

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    _enable_sqlite_foreign_keys(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    login_manager.session_protection = "strong"

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .blueprints import api, auth, citizen, media, public, staff
    app.register_blueprint(public.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(citizen.bp)
    app.register_blueprint(staff.bp)
    app.register_blueprint(media.bp)
    app.register_blueprint(api.bp)

    from . import cli
    cli.register(app)

    _register_template_helpers(app)
    _register_errors(app)
    _security_headers(app)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return app


def _enable_sqlite_foreign_keys(app: Flask) -> None:
    """SQLite ignores foreign keys unless enabled per connection."""
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    if event.contains(Engine, "connect", _fk_pragma):
        return
    event.listen(Engine, "connect", _fk_pragma)


def _fk_pragma(dbapi_conn, _record):
    if dbapi_conn.__class__.__module__.startswith("sqlite3"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def _register_template_helpers(app: Flask) -> None:
    from .categories import CATEGORIES, label
    from .services.workflow import STATUS_LABELS

    tz = ZoneInfo(app.config["DISPLAY_TZ"])

    @app.template_filter("local")
    def local_time(dt, fmt="%d %b %Y, %I:%M %p"):
        if dt is None:
            return "—"
        return dt.replace(tzinfo=timezone.utc).astimezone(tz).strftime(fmt) + " IST"

    @app.context_processor
    def inject():
        unread = 0
        if current_user.is_authenticated:
            from .models import Notification
            unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {"CATEGORIES": CATEGORIES, "category_label": label, "STATUS_LABELS": STATUS_LABELS,
                "unread_notifications": unread}


def _register_errors(app: Flask) -> None:
    for code in (400, 403, 404, 413, 429, 500):
        def handler(e, code=code):
            return render_template("error.html", code=code, error=e), code
        app.register_error_handler(code, handler)


def _security_headers(app: Flask) -> None:
    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
        return resp
