import re
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db, limiter
from ..models import AuditEvent, Role, User

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_password(pw: str) -> str | None:
    if len(pw) < 10:
        return "Password must be at least 10 characters."
    if len(pw) > 128:
        return "Password is too long."
    if pw.isalpha() or pw.isdigit():
        return "Use a mix of letters and numbers or symbols."
    return None


def _safe_next(target: str | None) -> str | None:
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def home_for(user) -> str:
    return url_for("staff.dashboard") if user.is_staff else url_for("citizen.dashboard")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["REGISTER_RATE_LIMIT"], methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    errors, form = {}, {}
    if request.method == "POST":
        form = {"email": request.form.get("email", "").strip().lower(),
                "display_name": request.form.get("display_name", "").strip()}
        pw = request.form.get("password", "")
        pw2 = request.form.get("password2", "")
        if not EMAIL_RE.match(form["email"]) or len(form["email"]) > 254:
            errors["email"] = "Enter a valid email address."
        elif User.query.filter_by(email=form["email"]).first():
            errors["email"] = "An account with this email already exists."
        if not (2 <= len(form["display_name"]) <= 80):
            errors["display_name"] = "Name must be 2–80 characters."
        if (msg := validate_password(pw)):
            errors["password"] = msg
        elif pw != pw2:
            errors["password2"] = "Passwords do not match."
        if not request.form.get("accept_terms"):
            errors["accept_terms"] = "Please confirm you have read the privacy notice."
        if not errors:
            user = User(email=form["email"], display_name=form["display_name"], role=Role.CITIZEN)
            user.set_password(pw)
            db.session.add(user)
            db.session.flush()
            db.session.add(AuditEvent(actor_id=user.id, action="user.register", target=f"user:{user.id}"))
            db.session.commit()
            login_user(user)
            flash("Account created. Welcome to CivicEye.", "success")
            return redirect(url_for("citizen.dashboard"))
    return render_template("auth/register.html", errors=errors, form=form), (400 if errors else 200)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"], methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    error = None
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.is_active_account and user.check_password(pw):
            login_user(user)
            db.session.add(AuditEvent(actor_id=user.id, action="user.login", target=f"user:{user.id}"))
            db.session.commit()
            return redirect(_safe_next(request.args.get("next")) or home_for(user))
        error = "Incorrect email or password."  # same message for unknown accounts
    return render_template("auth/login.html", error=error, email=email), (401 if error else 200)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have signed out.", "info")
    return redirect(url_for("public.home"))
